"""
Authentication Router
Handles all authentication-related endpoints:
- Registration, login, logout
- Password reset
- Email verification
- MFA (TOTP and Email)
- User profile
"""

import asyncio
import json
import logging
import secrets
from datetime import datetime, timedelta
from typing import Union

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from auth.dependencies import get_current_active_user
from auth.models import (
    FontSizeUpdateRequest,
    MFAEnableRequest,
    MFAEnableResponse,
    MFARequiredResponse,
    MFASetupResponse,
    MFAStatusResponse,
    MFAVerifyRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshTokenRequest,
    ReportTabOrderRequest,
    ThemeUpdateRequest,
    TokenResponse,
    UserLogin,
    UserRegister,
    UserResponse,
    UserUpdate,
)
from auth.service import AuthService
from database import User, get_db
from email_service import email_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])
limiter = Limiter(key_func=get_remote_address)


# =============================================================================
# REGISTRATION & EMAIL VERIFICATION
# =============================================================================


@router.post("/register", response_model=UserResponse, status_code=201)
@limiter.limit("5/hour")
async def register_user(
    request: Request, user_data: UserRegister, db: Session = Depends(get_db)
):
    """
    Register a new user

    Creates a new user account with email and password.
    Automatically creates a trial subscription.

    Rate limit: 5 registrations per hour per IP
    """
    try:
        user, tokens = AuthService.register_user(user_data, db)

        # Return user info and set tokens in response headers
        response = JSONResponse(
            content={
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "company_name": user.company_name,
                "cnpj": user.cnpj,
                "is_active": user.is_active,
                "is_verified": user.is_verified,
                "created_at": user.created_at.isoformat() + "Z" if user.created_at else None,
                "access_token": tokens.access_token,
                "refresh_token": tokens.refresh_token,
            },
            status_code=201,
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(status_code=500, detail="Falha no cadastro. Tente novamente.")


@router.get("/verify-email")
async def verify_email(token: str, db: Session = Depends(get_db)):
    """Verify user email with token"""
    user = db.query(User).filter(User.email_verification_token == token).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token de verificação inválido ou expirado",
        )

    # Check if token has expired (24 hours)
    if user.email_verification_token_created_at:
        token_age = datetime.utcnow() - user.email_verification_token_created_at
        if token_age > timedelta(hours=24):
            # Clear expired token
            user.email_verification_token = None
            user.email_verification_token_created_at = None
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token de verificação expirado. Solicite um novo e-mail de verificação.",
            )

    # Update user
    user.is_verified = True
    user.email_verified_at = datetime.utcnow()
    user.email_verification_token = None  # Clear token after use
    user.email_verification_token_created_at = None

    db.commit()

    return {
        "message": "E-mail verificado com sucesso!",
        "email": user.email,
        "verified": True,
    }


@router.post("/resend-verification")
@limiter.limit("3/hour")
async def resend_verification(
    request: Request, email_data: dict, db: Session = Depends(get_db)
):
    """Resend verification email"""
    email = email_data.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="E-mail é obrigatório"
        )

    user = db.query(User).filter(User.email == email).first()

    if not user:
        # Don't reveal if email exists
        return {"message": "Se o e-mail estiver cadastrado, você receberá um novo link de verificação."}

    if user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="E-mail já verificado",
        )

    # Generate new token with timestamp
    new_token = secrets.token_urlsafe(32)
    user.email_verification_token = new_token
    user.email_verification_token_created_at = datetime.utcnow()
    db.commit()

    # Send verification email
    try:
        asyncio.create_task(
            email_service.send_verification_email(
                to=user.email,
                token=new_token,
                user_name=user.full_name or user.email.split("@")[0],
            )
        )
    except Exception as e:
        logger.error(f"Failed to send verification email: {e}")

    return {"message": "E-mail de verificação enviado!"}


# =============================================================================
# CNPJ LOOKUP — Priority: BrasilAPI (free) → SERPRO (official) → ReceitaWS
# =============================================================================

# Module-level cache for SERPRO OAuth2 token (1-hour validity)
_serpro_token_cache: dict = {"token": None, "expires_at": 0}


def _extract_regime_tributario(raw) -> str | None:
    """
    BrasilAPI returns regime_tributario as a list of dicts with yearly history:
      [{"ano": 2022, "forma_de_tributacao": "LUCRO PRESUMIDO", ...}, ...]
    Extract the most recent year's forma_de_tributacao as a simple string.
    If it's already a string (SERPRO/ReceitaWS), return as-is.
    """
    if not raw:
        return None
    if isinstance(raw, str):
        return raw[:100]
    if isinstance(raw, list):
        try:
            # Sort by year descending, pick the latest
            sorted_entries = sorted(raw, key=lambda x: x.get("ano", 0), reverse=True)
            latest = sorted_entries[0].get("forma_de_tributacao", "")
            return str(latest)[:100] if latest else None
        except (IndexError, TypeError, AttributeError):
            return None
    return str(raw)[:100]


@router.get("/lookup-cnpj/{cnpj}")
@limiter.limit("15/minute")
async def lookup_cnpj(request: Request, cnpj: str):
    """
    Lookup CNPJ data. Priority: BrasilAPI (free) → SERPRO (when configured) → ReceitaWS.
    Public proxy endpoint — the browser cannot call external APIs directly due to CORS.
    Returns comprehensive company data for auto-fill on registration/profile.
    """
    import httpx
    import re as _re
    import base64
    import time

    from config import settings

    cnpj_digits = _re.sub(r'\D', '', cnpj)
    if len(cnpj_digits) != 14:
        raise HTTPException(status_code=400, detail="CNPJ deve ter 14 dígitos")

    # ── SERPRO (official Receita Federal data via OAuth2) ──────────────────
    async def _get_serpro_token(client: httpx.AsyncClient) -> str | None:
        """Get or refresh SERPRO OAuth2 bearer token (cached for 1 hour)."""
        if _serpro_token_cache["token"] and time.time() < _serpro_token_cache["expires_at"]:
            return _serpro_token_cache["token"]

        key = settings.serpro_consumer_key
        secret = settings.serpro_consumer_secret
        if not key or not secret:
            return None

        try:
            credentials = base64.b64encode(f"{key}:{secret}".encode()).decode()
            resp = await client.post(
                "https://gateway.apiserpro.serpro.gov.br/token",
                headers={
                    "Authorization": f"Basic {credentials}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data="grant_type=client_credentials",
                timeout=10.0,
            )
            if resp.status_code != 200:
                logger.warning(f"SERPRO token request failed: {resp.status_code}")
                return None
            token_data = resp.json()
            token = token_data.get("access_token")
            # Cache for 50 minutes (token valid for 60, leave buffer)
            _serpro_token_cache["token"] = token
            _serpro_token_cache["expires_at"] = time.time() + 3000
            return token
        except Exception as e:
            logger.warning(f"SERPRO token error: {e}")
            return None

    async def _try_serpro(client: httpx.AsyncClient) -> dict | None:
        """Try SERPRO official API (requires configured credentials)."""
        token = await _get_serpro_token(client)
        if not token:
            return None

        try:
            base_url = settings.serpro_api_url.rstrip("/")
            resp = await client.get(
                f"{base_url}/empresa/{cnpj_digits}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                },
                timeout=10.0,
            )
            if resp.status_code == 401:
                # Token expired, clear cache and skip
                _serpro_token_cache["token"] = None
                _serpro_token_cache["expires_at"] = 0
                return None
            if resp.status_code != 200:
                return None

            d = resp.json()
            # Parse SERPRO response format
            cnae_p = d.get("cnaePrincipal", {})
            endereco = d.get("endereco", {})
            telefones = d.get("telefone", [])
            tel_str = ""
            if telefones and isinstance(telefones, list) and len(telefones) > 0:
                t = telefones[0]
                tel_str = f"({t.get('ddd', '')}) {t.get('numero', '')}" if isinstance(t, dict) else str(t)

            # Parse situacao
            situacao = d.get("situacaoCadastral", {})
            situacao_desc = situacao.get("descricao", "") if isinstance(situacao, dict) else str(situacao)

            # Parse natureza juridica
            nat_jur = d.get("naturezaJuridica", {})
            nat_jur_desc = f"{nat_jur.get('codigo', '')} - {nat_jur.get('descricao', '')}" if isinstance(nat_jur, dict) else str(nat_jur)

            # Parse porte
            porte_map = {"01": "Microempresa", "03": "Empresa de Pequeno Porte", "05": "Demais"}
            porte_raw = d.get("porte", "")
            porte_desc = porte_map.get(str(porte_raw), str(porte_raw))

            # Parse Simples/MEI from informacoesAdicionais
            info_add = d.get("informacoesAdicionais", {}) or {}
            simples = info_add.get("optanteSimples") if isinstance(info_add, dict) else None
            mei = info_add.get("optanteMEI") if isinstance(info_add, dict) else None

            return {
                "nome": d.get("nomeEmpresarial"),
                "fantasia": d.get("nomeFantasia") or None,
                "cnpj": cnpj_digits,
                "situacao": situacao_desc,
                "porte": porte_desc,
                "natureza_juridica": nat_jur_desc,
                "cnae_code": cnae_p.get("codigo") if isinstance(cnae_p, dict) else None,
                "cnae_description": cnae_p.get("descricao") if isinstance(cnae_p, dict) else None,
                "abertura": d.get("dataAbertura"),
                "logradouro": f"{endereco.get('tipoLogradouro', '')} {endereco.get('logradouro', '')}".strip() if isinstance(endereco, dict) else None,
                "numero": endereco.get("numero") if isinstance(endereco, dict) else None,
                "complemento": endereco.get("complemento") or None if isinstance(endereco, dict) else None,
                "bairro": endereco.get("bairro") if isinstance(endereco, dict) else None,
                "municipio": endereco.get("municipio", {}).get("descricao") if isinstance(endereco, dict) and isinstance(endereco.get("municipio"), dict) else None,
                "uf": endereco.get("uf") if isinstance(endereco, dict) else None,
                "cep": endereco.get("cep") if isinstance(endereco, dict) else None,
                "capital_social": d.get("capitalSocial"),
                "telefone": tel_str,
                "email": d.get("correioEletronico") or None,
                "simples_nacional": simples,
                "mei": mei,
                "source": "serpro",
            }
        except Exception as e:
            logger.warning(f"SERPRO lookup failed: {e}")
            return None

    # ── BrasilAPI (free, no auth) ─────────────────────────────────────────
    async def _try_brasilapi(client: httpx.AsyncClient) -> dict | None:
        """Try BrasilAPI (free, no auth, comprehensive)."""
        try:
            resp = await client.get(f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_digits}")
            if resp.status_code != 200:
                return None
            d = resp.json()
            cnae_code = str(d.get("cnae_fiscal", "")) if d.get("cnae_fiscal") else None
            cnae_desc = d.get("cnae_fiscal_descricao", None)
            phone_ddd = d.get("ddd_telefone_1", "")

            # Parse QSA (partners/shareholders)
            qsa_raw = d.get("qsa", []) or []
            qsa_partners = []
            main_partner_name = None
            main_partner_qual = None
            for socio in qsa_raw:
                partner = {
                    "nome": socio.get("nome_socio"),
                    "qualificacao": socio.get("qualificacao_socio"),
                    "data_entrada": socio.get("data_entrada_sociedade"),
                    "cpf_cnpj": socio.get("cnpj_cpf_do_socio"),
                    "faixa_etaria": socio.get("faixa_etaria"),
                }
                qsa_partners.append(partner)
                # Find main partner: prefer "Sócio-Administrador" (code 49)
                qual = socio.get("qualificacao_socio", "")
                if main_partner_name is None or "Administrador" in (qual or ""):
                    main_partner_name = socio.get("nome_socio")
                    main_partner_qual = qual

            # Parse secondary CNAEs
            cnaes_sec_raw = d.get("cnaes_secundarios", []) or []
            cnaes_secundarios = [
                {"codigo": c.get("codigo"), "descricao": c.get("descricao")}
                for c in cnaes_sec_raw if c.get("codigo")
            ]

            # Parse address type
            address_type = d.get("descricao_tipo_de_logradouro", None)
            logradouro = d.get("logradouro", "")
            if address_type and logradouro and not logradouro.lower().startswith(address_type.lower()):
                logradouro = f"{address_type} {logradouro}"

            # Headquarters vs branch
            id_matriz = d.get("identificador_matriz_filial")
            is_headquarters = (id_matriz == 1) if id_matriz is not None else None

            return {
                "nome": d.get("razao_social"),
                "fantasia": d.get("nome_fantasia") or None,
                "cnpj": cnpj_digits,
                "situacao": d.get("descricao_situacao_cadastral"),
                "porte": d.get("porte") or d.get("descricao_porte"),
                "natureza_juridica": d.get("natureza_juridica"),
                "cnae_code": cnae_code,
                "cnae_description": cnae_desc,
                "abertura": d.get("data_inicio_atividade"),
                "logradouro": logradouro,
                "numero": d.get("numero"),
                "complemento": d.get("complemento") or None,
                "bairro": d.get("bairro"),
                "municipio": d.get("municipio"),
                "uf": d.get("uf"),
                "cep": d.get("cep"),
                "capital_social": d.get("capital_social"),
                "telefone": phone_ddd,
                "email": d.get("email") or None,
                "simples_nacional": d.get("opcao_pelo_simples"),
                "mei": d.get("opcao_pelo_mei"),
                # New fields
                "qsa_partners": qsa_partners,
                "cnaes_secundarios": cnaes_secundarios,
                "address_type": address_type,
                "is_headquarters": is_headquarters,
                "ibge_code": str(d.get("codigo_municipio_ibge", "")) if d.get("codigo_municipio_ibge") else None,
                "regime_tributario": _extract_regime_tributario(d.get("regime_tributario")),
                "simples_desde": d.get("data_opcao_pelo_simples"),
                "simples_excluido_em": d.get("data_exclusao_do_simples"),
                "main_partner_name": main_partner_name,
                "main_partner_qualification": main_partner_qual,
                "source": "brasilapi",
            }
        except Exception as e:
            logger.warning(f"BrasilAPI lookup failed: {e}")
            return None

    # ── ReceitaWS (last resort fallback) ──────────────────────────────────
    async def _try_receitaws(client: httpx.AsyncClient) -> dict | None:
        """Fallback to ReceitaWS."""
        try:
            resp = await client.get(f"https://receitaws.com.br/v1/cnpj/{cnpj_digits}")
            if resp.status_code == 429:
                return None
            d = resp.json()
            if d.get("status") == "ERROR":
                return None
            atv = d.get("atividade_principal", [{}])
            cnae_code = atv[0].get("code") if atv else None
            cnae_desc = atv[0].get("text") if atv else None
            phone = d.get("telefone", "")
            return {
                "nome": d.get("nome"),
                "fantasia": d.get("fantasia") or None,
                "cnpj": d.get("cnpj"),
                "situacao": d.get("situacao"),
                "porte": d.get("porte"),
                "natureza_juridica": d.get("natureza_juridica"),
                "cnae_code": cnae_code,
                "cnae_description": cnae_desc,
                "abertura": d.get("abertura"),
                "logradouro": d.get("logradouro"),
                "numero": d.get("numero"),
                "complemento": d.get("complemento") or None,
                "bairro": d.get("bairro"),
                "municipio": d.get("municipio"),
                "uf": d.get("uf"),
                "cep": d.get("cep"),
                "capital_social": float(d.get("capital_social", "0").replace(".", "").replace(",", ".")) if d.get("capital_social") else None,
                "telefone": phone,
                "email": d.get("email") or None,
                "simples_nacional": d.get("simples", {}).get("optante") if isinstance(d.get("simples"), dict) else None,
                "mei": d.get("simei", {}).get("optante") if isinstance(d.get("simei"), dict) else None,
                "source": "receitaws",
            }
        except Exception as e:
            logger.warning(f"ReceitaWS lookup failed: {e}")
            return None

    # ── Execute with priority chain ───────────────────────────────────────
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # 1. BrasilAPI (free, comprehensive, default)
            result = await _try_brasilapi(client)
            # 2. SERPRO (official, when credentials configured)
            if result is None:
                result = await _try_serpro(client)
            # 3. ReceitaWS (last resort)
            if result is None:
                result = await _try_receitaws(client)

        if result is None:
            raise HTTPException(status_code=404, detail="CNPJ não encontrado")

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"CNPJ lookup error: {e}")
        raise HTTPException(status_code=502, detail="Erro ao consultar dados do CNPJ. Tente novamente.")


# =============================================================================
# CNPJ EXTRACTION (Public, API-key protected for registration)
# =============================================================================


@router.post("/extract-cnpj")
@limiter.limit("10/hour")
async def extract_cnpj_from_card(request: Request):
    """
    Extract CNPJ from an uploaded card image/PDF.
    Public endpoint (no JWT) but protected by API key to prevent abuse.
    Used during registration before user has an account.
    """
    from fastapi import File, UploadFile, Header
    import tempfile
    import os
    from config import settings
    from cnpj_validator import extract_cnpj_from_document, format_cnpj

    # Verify API key if configured (use 403, not 401 — 401 triggers JWT refresh interceptors)
    # If api_key is not set in config, allow access (rate limiting still applies)
    if settings.api_key:
        api_key = request.headers.get("x-api-key", "")
        if not api_key or api_key != settings.api_key:
            raise HTTPException(status_code=403, detail="Chave de API inválida")

    # Get the file from multipart form
    form = await request.form()
    file = form.get("file")
    if not file:
        raise HTTPException(status_code=400, detail="Arquivo é obrigatório")

    # Validate file type
    filename = getattr(file, "filename", "") or ""
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext not in ("pdf", "jpg", "jpeg", "png", "webp"):
        raise HTTPException(
            status_code=400,
            detail="Formato inválido. Envie PDF, JPG, PNG ou WebP."
        )

    # Save to temp file
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(status_code=400, detail="Arquivo muito grande (máx 10MB)")

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        # Extract CNPJ using AI (key pool for round-robin + failover across all providers)
        from ai_key_pool import get_next_ai_credentials
        import routers.documents as docs_router
        _pool = getattr(getattr(docs_router, 'processor', None), 'key_pool', None)
        if _pool is None:
            from structured_processor import StructuredDocumentProcessor
            _pool = StructuredDocumentProcessor().key_pool
        _provider, _api_key, _model = get_next_ai_credentials(
            _pool, preferred_provider=settings.ai_provider
        )
        recipient_cnpj, sender_cnpj = extract_cnpj_from_document(
            tmp_path,
            ai_provider=_provider,
            api_key=_api_key,
            model=_model,
        )

        cnpj = recipient_cnpj or sender_cnpj
        if not cnpj:
            return {"success": False, "cnpj": None, "company_name": None, "message": "CNPJ não encontrado no documento"}

        return {
            "success": True,
            "cnpj": format_cnpj(cnpj),
            "cnpj_raw": cnpj,
            "company_name": None,  # Could add ReceitaWS lookup here later
        }
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


# =============================================================================
# LOGIN & LOGOUT
# =============================================================================


@router.post("/login")
@limiter.limit("10/hour")
async def login_user(
    request: Request, login_data: UserLogin, db: Session = Depends(get_db)
) -> Union[TokenResponse, MFARequiredResponse]:
    """
    Authenticate user and return JWT tokens or MFA required response

    Rate limit: 10 login attempts per hour per IP
    Creates session with device tracking and enforces 2-device limit.
    If MFA is enabled and device is not trusted, returns MFA required response.
    """
    try:
        # Get user agent and IP for session tracking
        user_agent = request.headers.get("User-Agent", "Unknown")
        ip_address = request.client.host if request.client else "Unknown"

        # Authenticate and create session
        tokens = AuthService.login_user(login_data, user_agent, ip_address, db)
        return tokens
    except HTTPException as e:
        # Check if this is an MFA required response (status 202)
        if e.status_code == status.HTTP_202_ACCEPTED and isinstance(e.detail, dict):
            return MFARequiredResponse(**e.detail)
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail="Falha no login")


@router.post("/mfa/verify-login", response_model=TokenResponse)
@limiter.limit("10/hour")
async def verify_mfa_login(
    request: Request,
    temp_token: str,
    mfa_code: str,
    trust_device: bool = False,
    db: Session = Depends(get_db)
):
    """
    Verify MFA code during login and issue full tokens

    Args:
        temp_token: Temporary token from initial login
        mfa_code: 6-digit MFA code (TOTP, Email, or backup code)
        trust_device: Whether to trust this device for 30 days
    """
    try:
        user_agent = request.headers.get("User-Agent", "Unknown")
        ip_address = request.client.host if request.client else "Unknown"

        tokens = AuthService.verify_mfa_login(
            temp_token=temp_token,
            mfa_code=mfa_code,
            trust_device=trust_device,
            user_agent=user_agent,
            ip_address=ip_address,
            db=db
        )
        return tokens
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"MFA verification error: {e}")
        raise HTTPException(status_code=500, detail="Falha na verificação")


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    refresh_data: RefreshTokenRequest, db: Session = Depends(get_db)
):
    """Refresh access token using refresh token"""
    try:
        tokens = AuthService.refresh_access_token(refresh_data.refresh_token, db)
        return tokens
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token refresh error: {e}")
        raise HTTPException(status_code=500, detail="Falha ao atualizar token")


@router.post("/logout")
async def logout_user(
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Logout user - revokes the current session server-side.

    The JWT token's embedded session_id (sid) is used to identify
    and deactivate the session, making the token immediately invalid.
    """
    from auth.security import verify_token as _verify_token
    from auth.session_manager import SessionManager

    # Extract session_id from the current token
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        payload = _verify_token(token, token_type="access")
        session_id = payload.get("sid") if payload else None

        if session_id:
            SessionManager.revoke_session(session_id, db)

    return {"message": "Logged out successfully"}


# =============================================================================
# PASSWORD RESET
# =============================================================================


@router.post("/password-reset/request")
@limiter.limit("3/hour")
async def request_password_reset(
    request: Request, reset_request: PasswordResetRequest, db: Session = Depends(get_db)
):
    """
    Request password reset

    Generates a reset token and sends email.
    Rate limit: 3 requests per hour per IP
    """
    try:
        token = AuthService.request_password_reset(reset_request.email, db)

        # Always return success to prevent email enumeration
        # Token is sent only via email, never in the API response
        return {
            "message": "If the email exists, a password reset link has been sent",
        }
    except HTTPException:
        # Always return success to prevent email enumeration
        return {"message": "If the email exists, a password reset link has been sent"}
    except Exception as e:
        logger.error(f"Password reset request error: {e}")
        return {"message": "If the email exists, a password reset link has been sent"}


@router.post("/password-reset/confirm")
async def confirm_password_reset(
    reset_data: PasswordResetConfirm, db: Session = Depends(get_db)
):
    """Confirm password reset with token"""
    try:
        AuthService.confirm_password_reset(
            reset_data.token, reset_data.new_password, db
        )
        return {"message": "Password reset successful"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Password reset confirmation error: {e}")
        raise HTTPException(status_code=500, detail="Falha ao redefinir senha")


# =============================================================================
# USER PROFILE
# =============================================================================


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_active_user)):
    """Get current authenticated user information"""
    return current_user


@router.patch("/me", response_model=UserResponse)
async def update_user_profile(
    update_data: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Update current user profile (full_name, company_name, cnpj)"""
    try:
        updated_user = AuthService.update_user_profile(
            current_user, update_data.model_dump(exclude_unset=True), db
        )
        return updated_user
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Profile update error: {e}")
        raise HTTPException(status_code=500, detail="Falha ao atualizar perfil")


@router.patch("/me/theme")
async def update_theme_preference(
    theme_data: ThemeUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Update user's theme preference (light, dark, system)"""
    current_user.theme_preference = theme_data.theme
    db.commit()
    db.refresh(current_user)

    return {"theme": theme_data.theme, "message": "Theme preference updated successfully"}


@router.patch("/me/font-size")
async def update_font_size_preference(
    data: FontSizeUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Update user's font size preference per device type (mobile/desktop)"""
    if data.device == "mobile":
        current_user.font_size_mobile = data.size
    else:
        current_user.font_size_desktop = data.size

    db.commit()
    db.refresh(current_user)

    return {"size": data.size, "device": data.device, "message": "Font size preference updated"}


@router.patch("/me/report-tab-order")
async def update_report_tab_order(
    data: ReportTabOrderRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Update user's preferred report tab order"""
    current_user.report_tab_order = data.order
    db.commit()
    db.refresh(current_user)

    return {"order": current_user.report_tab_order, "message": "Report tab order updated"}


# =============================================================================
# MFA (MULTI-FACTOR AUTHENTICATION)
# =============================================================================


@router.post("/mfa/setup/totp")
async def setup_totp_mfa(
    current_user: User = Depends(get_current_active_user),
):
    """
    Generate TOTP secret and QR code for Google Authenticator setup

    Returns secret and provisioning URI for QR code generation.
    User must verify the code with /auth/mfa/enable before enabling.
    """
    from auth.mfa_service import MFAService

    # Generate new secret
    secret = MFAService.generate_totp_secret()

    # Get provisioning URI for QR code
    provisioning_uri = MFAService.get_totp_provisioning_uri(
        user_email=current_user.email,
        secret=secret,
        issuer="ControlladorIA"
    )

    return MFASetupResponse(
        secret=secret,
        provisioning_uri=provisioning_uri
    )


@router.post("/mfa/verify/totp")
async def verify_totp_setup(
    verify_data: MFAVerifyRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Verify TOTP code during setup (test verification)"""
    return {"valid": True, "message": "Use /auth/mfa/enable to complete setup"}


@router.post("/mfa/enable")
async def enable_mfa(
    enable_data: MFAEnableRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Enable TOTP MFA after verifying code

    Generates backup codes and saves MFA configuration.
    Returns backup codes for user to save.
    """
    from auth.mfa_service import MFAService

    # Verify the code before enabling
    is_valid = MFAService.verify_totp_code(
        secret=enable_data.secret,
        code=enable_data.code
    )

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código inválido. Verifique o código e tente novamente."
        )

    # Generate backup codes
    backup_codes = MFAService.generate_backup_codes(count=10)

    # Enable MFA for user
    MFAService.enable_totp_mfa(
        user=current_user,
        secret=enable_data.secret,
        backup_codes=backup_codes,
        db=db
    )

    return MFAEnableResponse(
        backup_codes=backup_codes,
        message="Verificação em duas etapas ativada! Salve seus códigos de backup em local seguro."
    )


@router.post("/mfa/enable-email")
async def enable_email_mfa(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Enable Email MFA (no TOTP setup required)

    Generates backup codes and enables email-based MFA.
    User will receive 6-digit codes via email when logging in.
    """
    from auth.mfa_service import MFAService

    # Check if MFA is already enabled
    if current_user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verificação já está ativada. Desative primeiro para trocar de método."
        )

    # Generate backup codes
    backup_codes = MFAService.generate_backup_codes(count=10)

    # Enable Email MFA for user
    MFAService.enable_email_mfa(
        user=current_user,
        backup_codes=backup_codes,
        db=db
    )

    return MFAEnableResponse(
        backup_codes=backup_codes,
        message="Verificação por Email ativada! Você receberá códigos no seu email ao fazer login."
    )


@router.post("/mfa/disable")
async def disable_mfa(
    password: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Disable MFA (requires password confirmation)"""
    from auth.mfa_service import MFAService
    from auth.security import verify_password

    # Verify password before disabling MFA
    if not verify_password(password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Senha incorreta"
        )

    # Disable MFA
    MFAService.disable_mfa(user=current_user, db=db)

    return {"message": "Verificação em duas etapas desativada"}


@router.post("/mfa/send-email-code")
async def send_email_mfa_code(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Send MFA code via email

    Generates and emails a 6-digit code valid for 10 minutes.
    """
    from auth.mfa_service import MFAService

    # Generate code
    code = MFAService.generate_email_code()

    # Store code temporarily (10 min expiration)
    MFAService.store_email_code(
        user_id=current_user.id,
        code=code,
        expires_in_minutes=10
    )

    # Send email
    await MFAService.send_email_mfa_code(
        user=current_user,
        code=code
    )

    return {
        "message": "Código enviado para seu email",
        "expires_in": "10 minutos"
    }


@router.get("/mfa/status")
async def get_mfa_status(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get MFA status for current user"""
    backup_codes_remaining = 0
    if current_user.mfa_backup_codes:
        try:
            codes = json.loads(current_user.mfa_backup_codes)
            backup_codes_remaining = len(codes)
        except:
            pass

    return MFAStatusResponse(
        enabled=current_user.mfa_enabled,
        method=current_user.mfa_method,
        enabled_at=current_user.mfa_enabled_at,
        backup_codes_remaining=backup_codes_remaining
    )
