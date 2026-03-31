"""
Unit tests for Account Router

Tests client/supplier/customer management:
- List clients with filtering
- Create client
- Update client
- Delete client (soft delete)
- Multi-tenant isolation
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from database import Client, User
from api import app

client = TestClient(app)


class TestListClients:
    """Test listing clients with filters"""

    @patch("routers.account.get_current_active_user")
    @patch("routers.account.get_accessible_user_ids")
    @patch("routers.account.get_db")
    def test_list_all_clients(
        self, mock_db, mock_accessible_ids, mock_current_user
    ):
        """Test listing all clients for current user"""
        mock_user = MagicMock(spec=User)
        mock_user.id = 1
        mock_current_user.return_value = mock_user
        mock_accessible_ids.return_value = [1]

        mock_db_session = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_db_session

        # Mock clients
        client1 = MagicMock(spec=Client)
        client1.id = 1
        client1.name = "Test Client"
        client1.legal_name = "Test Client Ltd"
        client1.tax_id = "12345678000190"
        client1.email = "client@test.com"
        client1.phone = "11999999999"
        client1.address = "Test St, 123"
        client1.client_type = "customer"
        client1.created_at = datetime.utcnow()

        mock_query = mock_db_session.query.return_value
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 1
        mock_query.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [
            client1
        ]

        response = client.get("/clients")

        assert response.status_code == 200
        data = response.json()
        assert "clients" in data
        assert "total" in data
        assert data["total"] == 1
        assert len(data["clients"]) == 1
        assert data["clients"][0]["name"] == "Test Client"

    @patch("routers.account.get_current_active_user")
    @patch("routers.account.get_accessible_user_ids")
    @patch("routers.account.get_db")
    def test_list_clients_filter_by_type(
        self, mock_db, mock_accessible_ids, mock_current_user
    ):
        """Test filtering clients by type"""
        mock_user = MagicMock(spec=User)
        mock_user.id = 1
        mock_current_user.return_value = mock_user
        mock_accessible_ids.return_value = [1]

        mock_db_session = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_db_session

        mock_query = mock_db_session.query.return_value
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 0
        mock_query.order_by.return_value.offset.return_value.limit.return_value.all.return_value = (
            []
        )

        response = client.get("/clients?client_type=supplier")

        assert response.status_code == 200
        # Verify filter was applied
        mock_query.filter.assert_called()

    @patch("routers.account.get_current_active_user")
    @patch("routers.account.get_accessible_user_ids")
    @patch("routers.account.get_db")
    def test_list_clients_search(
        self, mock_db, mock_accessible_ids, mock_current_user
    ):
        """Test searching clients by name or tax ID"""
        mock_user = MagicMock(spec=User)
        mock_user.id = 1
        mock_current_user.return_value = mock_user
        mock_accessible_ids.return_value = [1]

        mock_db_session = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_db_session

        mock_query = mock_db_session.query.return_value
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 0
        mock_query.order_by.return_value.offset.return_value.limit.return_value.all.return_value = (
            []
        )

        response = client.get("/clients?search=Test")

        assert response.status_code == 200


class TestCreateClient:
    """Test creating new clients"""

    @patch("routers.account.get_current_active_user")
    @patch("routers.account.get_db")
    def test_create_client_success(self, mock_db, mock_current_user):
        """Test successful client creation"""
        mock_user = MagicMock(spec=User)
        mock_user.id = 1
        mock_current_user.return_value = mock_user

        mock_db_session = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_db_session

        # Mock the created client
        new_client = MagicMock(spec=Client)
        new_client.id = 1
        new_client.name = "New Client"

        response = client.post(
            "/clients",
            json={
                "name": "New Client",
                "legal_name": "New Client Ltd",
                "tax_id": "12345678000190",
                "email": "newclient@test.com",
                "phone": "11999999999",
                "address": "New St, 456",
                "client_type": "customer",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["name"] == "New Client"
        assert data["message"] == "Client created successfully"

    @patch("routers.account.get_current_active_user")
    @patch("routers.account.get_db")
    def test_create_supplier(self, mock_db, mock_current_user):
        """Test creating a supplier"""
        mock_user = MagicMock(spec=User)
        mock_user.id = 1
        mock_current_user.return_value = mock_user

        mock_db_session = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_db_session

        response = client.post(
            "/clients",
            json={
                "name": "Test Supplier",
                "client_type": "supplier",
            },
        )

        assert response.status_code == 201


class TestUpdateClient:
    """Test updating clients"""

    @patch("routers.account.get_current_active_user")
    @patch("routers.account.get_db")
    def test_update_client_success(self, mock_db, mock_current_user):
        """Test successful client update"""
        mock_user = MagicMock(spec=User)
        mock_user.id = 1
        mock_current_user.return_value = mock_user

        mock_db_session = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_db_session

        # Mock existing client
        existing_client = MagicMock(spec=Client)
        existing_client.id = 1
        existing_client.name = "Old Name"
        existing_client.user_id = 1

        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            existing_client
        )

        response = client.patch(
            "/clients/1",
            json={
                "name": "Updated Name",
                "email": "updated@test.com",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Client updated successfully"
        assert existing_client.name == "Updated Name"

    @patch("routers.account.get_current_active_user")
    @patch("routers.account.get_db")
    def test_update_client_not_found(self, mock_db, mock_current_user):
        """Test updating non-existent client"""
        mock_user = MagicMock(spec=User)
        mock_user.id = 1
        mock_current_user.return_value = mock_user

        mock_db_session = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_db_session
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        response = client.patch(
            "/clients/999",
            json={"name": "Updated Name"},
        )

        assert response.status_code == 404

    @patch("routers.account.get_current_active_user")
    @patch("routers.account.get_db")
    def test_update_other_users_client(self, mock_db, mock_current_user):
        """Test cannot update another user's client (multi-tenant isolation)"""
        mock_user = MagicMock(spec=User)
        mock_user.id = 1
        mock_current_user.return_value = mock_user

        mock_db_session = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_db_session

        # Client belongs to different user
        other_client = MagicMock(spec=Client)
        other_client.id = 1
        other_client.user_id = 999  # Different user
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        response = client.patch(
            "/clients/1",
            json={"name": "Hacked Name"},
        )

        assert response.status_code == 404  # Not found (security)


class TestDeleteClient:
    """Test deleting clients (soft delete)"""

    @patch("routers.account.get_current_active_user")
    @patch("routers.account.get_db")
    def test_delete_client_success(self, mock_db, mock_current_user):
        """Test successful client soft delete"""
        mock_user = MagicMock(spec=User)
        mock_user.id = 1
        mock_current_user.return_value = mock_user

        mock_db_session = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_db_session

        existing_client = MagicMock(spec=Client)
        existing_client.id = 1
        existing_client.name = "Client to Delete"
        existing_client.user_id = 1
        existing_client.is_active = True

        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            existing_client
        )

        response = client.delete("/clients/1")

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Client deleted successfully"
        assert data["id"] == 1
        # Verify soft delete (is_active = False)
        assert existing_client.is_active is False

    @patch("routers.account.get_current_active_user")
    @patch("routers.account.get_db")
    def test_delete_client_not_found(self, mock_db, mock_current_user):
        """Test deleting non-existent client"""
        mock_user = MagicMock(spec=User)
        mock_user.id = 1
        mock_current_user.return_value = mock_user

        mock_db_session = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_db_session
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        response = client.delete("/clients/999")

        assert response.status_code == 404
