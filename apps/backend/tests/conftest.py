from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_session
from app.core.security import hash_password
from app.core.database import Base
from app.main import create_application
from app.models.user import User


@pytest.fixture()
def db_session() -> Generator[sessionmaker[Session], None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    testing_session_local = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        class_=Session,
    )

    try:
        yield testing_session_local
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def client(db_session: sessionmaker[Session]) -> Generator[TestClient, None, None]:
    app = create_application()
    app.state.session_factory = db_session

    def override_get_session() -> Generator[Session, None, None]:
        session = db_session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_get_session

    bootstrap_session = db_session()
    try:
        admin_user = User(
            name="Test Admin",
            phone="+79990000001",
            password_hash=hash_password("password123"),
            roles=["admin"],
            is_active=True,
            created_at=1,
            updated_at=1,
            deleted_at=None,
            author_user_id=None,
        )
        bootstrap_session.add(admin_user)
        bootstrap_session.flush()
        admin_user.author_user_id = admin_user.id
        bootstrap_session.commit()
    finally:
        bootstrap_session.close()

    test_client = TestClient(app)
    try:
        login_response = test_client.post(
            "/api/auth/login",
            json={
                "phone": "+79990000001",
                "password": "password123",
            },
        )
        assert login_response.status_code == 200
        assert login_response.json()["status"] == "authenticated"
        yield test_client
    finally:
        test_client.close()
        app.dependency_overrides.clear()
