from fastapi.testclient import TestClient


def _create_user(client: TestClient, *, name: str, phone: str) -> dict:
    response = client.post(
        "/api/users",
        json={
            "name": name,
            "phone": phone,
            "roles": ["worker"],
            "is_active": True,
        },
    )
    assert response.status_code == 201
    return dict(response.json())


def _create_operation(client: TestClient, name: str) -> dict:
    response = client.post(
        "/api/operation-catalog",
        json={"name": name},
    )
    assert response.status_code == 201
    return dict(response.json())


def _add_skill(client: TestClient, user_id: int, operation_id: int) -> dict:
    response = client.post(
        f"/api/users/{user_id}/skills",
        json={"operation_catalog_entry_id": operation_id},
    )
    assert response.status_code == 200
    return dict(response.json())


def test_user_skills_support_unique_add_remove_and_hidden_inactive_entries(
    client: TestClient,
) -> None:
    """
    Проверяем управление навыками пользователя:
    - добавить уникальные активные операции и отклонить повтор
    - скрыть деактивированную операцию без удаления связи
    - удалить отображаемый навык и вернуть актуальные счётчики
    """
    worker = _create_user(
        client,
        name="Мастер навыков",
        phone="+79990000301",
    )
    sewing = _create_operation(client, "Навык пошива")
    cutting = _create_operation(client, "Навык кроя")

    _add_skill(client, worker["id"], sewing["id"])
    _add_skill(client, worker["id"], cutting["id"])
    duplicate_response = client.post(
        f"/api/users/{worker['id']}/skills",
        json={"operation_catalog_entry_id": sewing["id"]},
    )
    assert duplicate_response.status_code == 409
    assert duplicate_response.json()["detail"] == "Навык уже добавлен пользователю."

    deactivate_response = client.patch(
        f"/api/operation-catalog/{cutting['id']}/status",
        json={"is_active": False},
    )
    assert deactivate_response.status_code == 200

    skills_response = client.get(f"/api/users/{worker['id']}/skills")
    assert skills_response.status_code == 200
    skills = skills_response.json()
    assert [item["operation_catalog_entry_id"] for item in skills["skills"]] == [
        sewing["id"]
    ]
    assert skills["total_count"] == 2
    assert skills["hidden_inactive_count"] == 1

    remove_response = client.delete(
        f"/api/users/{worker['id']}/skills/{sewing['id']}"
    )
    assert remove_response.status_code == 200
    assert remove_response.json()["skills"] == []
    assert remove_response.json()["total_count"] == 1
    assert remove_response.json()["hidden_inactive_count"] == 1


def test_copy_user_skills_replaces_target_and_keeps_inactive_entries(
    client: TestClient,
) -> None:
    """
    Проверяем полное копирование навыков:
    - подготовить разные наборы источника и получателя
    - заменить навыки получателя набором источника
    - скопировать деактивированную связь и не показать её в форме
    """
    source = _create_user(
        client,
        name="Источник навыков",
        phone="+79990000302",
    )
    target = _create_user(
        client,
        name="Получатель навыков",
        phone="+79990000303",
    )
    source_active = _create_operation(client, "Активный навык источника")
    source_inactive = _create_operation(client, "Скрытый навык источника")
    target_only = _create_operation(client, "Старый навык получателя")
    _add_skill(client, source["id"], source_active["id"])
    _add_skill(client, source["id"], source_inactive["id"])
    _add_skill(client, target["id"], target_only["id"])
    deactivate_response = client.patch(
        f"/api/operation-catalog/{source_inactive['id']}/status",
        json={"is_active": False},
    )
    assert deactivate_response.status_code == 200

    copy_response = client.post(
        f"/api/users/{target['id']}/skills/copy",
        json={"source_user_id": source["id"]},
    )
    assert copy_response.status_code == 200
    copied = copy_response.json()
    assert [item["operation_catalog_entry_id"] for item in copied["skills"]] == [
        source_active["id"]
    ]
    assert copied["total_count"] == 2
    assert copied["hidden_inactive_count"] == 1

    users_response = client.get("/api/users")
    target_user = next(
        item for item in users_response.json() if item["id"] == target["id"]
    )
    assert target_user["skill_operation_catalog_entry_ids"] == sorted(
        [source_active["id"], source_inactive["id"]]
    )
    assert target_only["id"] not in target_user[
        "skill_operation_catalog_entry_ids"
    ]


def test_user_without_admin_role_cannot_manage_skills(client: TestClient) -> None:
    """
    Проверяем права формы навыков:
    - создать исполнителя и задать ему пароль
    - войти под исполнителем без роли администратора
    - запретить чтение навыков другого пользователя
    """
    worker = _create_user(
        client,
        name="Исполнитель без доступа",
        phone="+79990000304",
    )
    setup_response = client.post(
        "/api/auth/setup-password",
        json={
            "phone": worker["phone"],
            "new_password": "password123",
        },
    )
    assert setup_response.status_code == 200

    response = client.get("/api/users/1/skills")
    assert response.status_code == 403
    assert response.json()["detail"] == "Недостаточно прав."
