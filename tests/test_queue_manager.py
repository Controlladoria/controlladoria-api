"""
Tests for Document Queue Manager (Item 8 - Upload Queue)
Tests concurrent processing limits, queue ordering, and status reporting.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, Document, DocumentStatus
from tasks.queue_manager import (
    MAX_CONCURRENT,
    DocumentQueueManager,
    EnqueueResult,
    trigger_next_queued_document,
)


# ===== FIXTURES =====


@pytest.fixture
def db():
    """In-memory SQLite database for testing"""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()
    yield session
    session.close()


@pytest.fixture
def queue_manager(db):
    return DocumentQueueManager(db)


def create_test_document(db, status=DocumentStatus.PENDING, queue_position=None, user_id=1):
    """Helper to create a test document"""
    doc = Document(
        file_name="test.pdf",
        file_type="pdf",
        file_path="/tmp/test.pdf",
        file_size=1000,
        status=status,
        user_id=user_id,
        queue_position=queue_position,
        queued_at=datetime.utcnow() if queue_position else None,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


# ===== PROCESSING COUNT TESTS =====


def test_get_processing_count_empty(queue_manager):
    assert queue_manager.get_processing_count() == 0


def test_get_processing_count_with_processing_docs(db, queue_manager):
    create_test_document(db, status=DocumentStatus.PROCESSING)
    create_test_document(db, status=DocumentStatus.PROCESSING)
    create_test_document(db, status=DocumentStatus.PENDING)

    assert queue_manager.get_processing_count() == 2


def test_get_processing_count_ignores_other_statuses(db, queue_manager):
    create_test_document(db, status=DocumentStatus.COMPLETED)
    create_test_document(db, status=DocumentStatus.FAILED)
    create_test_document(db, status=DocumentStatus.PENDING)

    assert queue_manager.get_processing_count() == 0


# ===== QUEUE LENGTH TESTS =====


def test_get_queue_length_empty(queue_manager):
    assert queue_manager.get_queue_length() == 0


def test_get_queue_length_counts_queued_docs(db, queue_manager):
    create_test_document(db, status=DocumentStatus.PENDING, queue_position=1)
    create_test_document(db, status=DocumentStatus.PENDING, queue_position=2)
    # PENDING but not queued (no position)
    create_test_document(db, status=DocumentStatus.PENDING, queue_position=None)

    assert queue_manager.get_queue_length() == 2


# ===== QUEUE POSITION TESTS =====


def test_get_next_queue_position_empty(queue_manager):
    assert queue_manager.get_next_queue_position() == 1


def test_get_next_queue_position_increments(db, queue_manager):
    create_test_document(db, status=DocumentStatus.PENDING, queue_position=3)
    assert queue_manager.get_next_queue_position() == 4


# ===== ENQUEUE TESTS =====


def test_enqueue_immediate_when_under_limit(db, queue_manager):
    """Document should process immediately when under MAX_CONCURRENT"""
    doc = create_test_document(db)
    mock_bg = MagicMock()
    mock_func = MagicMock()

    result = queue_manager.enqueue(
        document_id=doc.id,
        file_path="/tmp/test.pdf",
        process_func=mock_func,
        background_tasks=mock_bg,
    )

    assert result.queued is False
    assert result.queue_position is None
    assert "imediatamente" in result.message
    mock_bg.add_task.assert_called_once_with(mock_func, doc.id, "/tmp/test.pdf")


def test_enqueue_queued_when_at_limit(db, queue_manager):
    """Document should be queued when at MAX_CONCURRENT"""
    # Fill all processing slots
    for _ in range(MAX_CONCURRENT):
        create_test_document(db, status=DocumentStatus.PROCESSING)

    doc = create_test_document(db)
    mock_bg = MagicMock()
    mock_func = MagicMock()

    result = queue_manager.enqueue(
        document_id=doc.id,
        file_path="/tmp/test.pdf",
        process_func=mock_func,
        background_tasks=mock_bg,
    )

    assert result.queued is True
    assert result.queue_position == 1
    assert "fila" in result.message
    assert "café" in result.message
    # Should NOT call background_tasks when queued
    mock_bg.add_task.assert_not_called()

    # Verify document was updated in DB
    db.refresh(doc)
    assert doc.queue_position == 1
    assert doc.queued_at is not None


def test_enqueue_queue_positions_increment(db, queue_manager):
    """Queue positions should increment for each queued document"""
    # Fill processing slots
    for _ in range(MAX_CONCURRENT):
        create_test_document(db, status=DocumentStatus.PROCESSING)

    doc1 = create_test_document(db)
    doc2 = create_test_document(db)

    mock_func = MagicMock()

    r1 = queue_manager.enqueue(doc1.id, "/tmp/1.pdf", mock_func)
    r2 = queue_manager.enqueue(doc2.id, "/tmp/2.pdf", mock_func)

    assert r1.queue_position == 1
    assert r2.queue_position == 2


def test_enqueue_exactly_at_limit(db, queue_manager):
    """At exactly MAX_CONCURRENT-1 processing, should still process immediately"""
    for _ in range(MAX_CONCURRENT - 1):
        create_test_document(db, status=DocumentStatus.PROCESSING)

    doc = create_test_document(db)
    mock_bg = MagicMock()
    mock_func = MagicMock()

    result = queue_manager.enqueue(doc.id, "/tmp/test.pdf", mock_func, mock_bg)

    assert result.queued is False
    mock_bg.add_task.assert_called_once()


def test_enqueue_without_background_tasks(db, queue_manager):
    """Enqueue should work without background_tasks (for testing)"""
    doc = create_test_document(db)
    mock_func = MagicMock()

    result = queue_manager.enqueue(
        document_id=doc.id,
        file_path="/tmp/test.pdf",
        process_func=mock_func,
        background_tasks=None,
    )

    assert result.queued is False
    assert result.document_id == doc.id


# ===== PROCESS_NEXT TESTS =====


def test_process_next_empty_queue(db, queue_manager):
    """process_next should return None when queue is empty"""
    mock_func = MagicMock()
    result = queue_manager.process_next(mock_func)
    assert result is None


def test_process_next_at_capacity(db, queue_manager):
    """process_next should return None when at capacity"""
    for _ in range(MAX_CONCURRENT):
        create_test_document(db, status=DocumentStatus.PROCESSING)

    create_test_document(db, status=DocumentStatus.PENDING, queue_position=1)

    mock_func = MagicMock()
    result = queue_manager.process_next(mock_func)
    assert result is None


def test_process_next_dequeues_first(db, queue_manager):
    """process_next should start the document with lowest queue position"""
    doc1 = create_test_document(db, status=DocumentStatus.PENDING, queue_position=2)
    doc2 = create_test_document(db, status=DocumentStatus.PENDING, queue_position=1)

    mock_func = MagicMock()

    with patch("tasks.queue_manager.threading") as mock_threading:
        mock_thread = MagicMock()
        mock_threading.Thread.return_value = mock_thread

        result = queue_manager.process_next(mock_func)

        assert result == doc2.id

        # Verify thread was started
        mock_thread.start.assert_called_once()

        # Verify thread was created with correct args
        mock_threading.Thread.assert_called_once()
        call_kwargs = mock_threading.Thread.call_args
        assert call_kwargs.kwargs["target"] == mock_func
        assert call_kwargs.kwargs["daemon"] is True

    # Verify queue position was cleared
    db.refresh(doc2)
    assert doc2.queue_position is None
    assert doc2.queued_at is None


def test_process_next_clears_queue_fields(db, queue_manager):
    """Dequeued document should have queue_position and queued_at cleared"""
    doc = create_test_document(db, status=DocumentStatus.PENDING, queue_position=1)

    mock_func = MagicMock()

    with patch("tasks.queue_manager.threading"):
        queue_manager.process_next(mock_func)

    db.refresh(doc)
    assert doc.queue_position is None
    assert doc.queued_at is None


# ===== QUEUE STATUS TESTS =====


def test_get_queue_status_empty(queue_manager):
    status = queue_manager.get_queue_status()

    assert status["processing_count"] == 0
    assert status["max_concurrent"] == MAX_CONCURRENT
    assert status["queue_length"] == 0
    assert status["slots_available"] == MAX_CONCURRENT
    assert status["estimated_wait_minutes"] == 0


def test_get_queue_status_with_activity(db, queue_manager):
    # 2 processing, 3 in queue
    create_test_document(db, status=DocumentStatus.PROCESSING)
    create_test_document(db, status=DocumentStatus.PROCESSING)
    create_test_document(db, status=DocumentStatus.PENDING, queue_position=1)
    create_test_document(db, status=DocumentStatus.PENDING, queue_position=2)
    create_test_document(db, status=DocumentStatus.PENDING, queue_position=3)

    status = queue_manager.get_queue_status()

    assert status["processing_count"] == 2
    assert status["queue_length"] == 3
    assert status["slots_available"] == MAX_CONCURRENT - 2
    assert status["estimated_wait_minutes"] == 6  # 3 * 2


# ===== DOCUMENT QUEUE POSITION TESTS =====


def test_get_document_queue_position(db, queue_manager):
    doc = create_test_document(db, status=DocumentStatus.PENDING, queue_position=5)
    assert queue_manager.get_document_queue_position(doc.id) == 5


def test_get_document_queue_position_not_queued(db, queue_manager):
    doc = create_test_document(db, status=DocumentStatus.PENDING)
    assert queue_manager.get_document_queue_position(doc.id) is None


# ===== TRIGGER NEXT TESTS =====


def test_trigger_next_queued_document_calls_process_next():
    """trigger_next_queued_document should create a session and call process_next"""
    mock_func = MagicMock()

    with patch("database.SessionLocal") as mock_session_local:
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        # Mock the query chain for process_next (get_processing_count returns 0)
        mock_db.query.return_value.filter.return_value.scalar.return_value = 0
        # Mock the next_doc query (no queued docs)
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = (
            None
        )

        result = trigger_next_queued_document(mock_func)
        assert result is None  # No queued docs

        # Verify session was closed
        mock_db.close.assert_called_once()


def test_trigger_next_handles_errors():
    """trigger_next_queued_document should handle errors gracefully"""
    mock_func = MagicMock()

    with patch("database.SessionLocal") as mock_session_local:
        mock_session_local.side_effect = Exception("DB connection failed")

        result = trigger_next_queued_document(mock_func)
        assert result is None


# ===== FULL FLOW TESTS =====


def test_full_flow_enqueue_process_dequeue(db, queue_manager):
    """Full flow: enqueue 4 docs (3 immediate, 1 queued), then dequeue"""
    docs = []
    mock_bg = MagicMock()
    mock_func = MagicMock()

    # Enqueue 4 documents
    for i in range(4):
        doc = create_test_document(db)
        docs.append(doc)

    # First 3 should process immediately
    for i in range(3):
        result = queue_manager.enqueue(docs[i].id, f"/tmp/{i}.pdf", mock_func, mock_bg)
        assert result.queued is False
        # Simulate that the document starts processing
        docs[i].status = DocumentStatus.PROCESSING
        db.commit()

    # 4th should be queued
    result = queue_manager.enqueue(docs[3].id, "/tmp/3.pdf", mock_func, mock_bg)
    assert result.queued is True
    assert result.queue_position == 1

    # Verify counts
    assert queue_manager.get_processing_count() == 3
    assert queue_manager.get_queue_length() == 1

    # Simulate first document completing
    docs[0].status = DocumentStatus.COMPLETED
    db.commit()

    # Now process_next should dequeue doc 4
    with patch("tasks.queue_manager.threading") as mock_threading:
        mock_thread = MagicMock()
        mock_threading.Thread.return_value = mock_thread

        next_id = queue_manager.process_next(mock_func)
        assert next_id == docs[3].id

    # Queue should now be empty
    assert queue_manager.get_queue_length() == 0


def test_max_concurrent_is_3():
    """Verify MAX_CONCURRENT is set to 3 as specified"""
    assert MAX_CONCURRENT == 3
