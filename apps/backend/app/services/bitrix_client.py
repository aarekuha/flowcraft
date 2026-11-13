# ruff: noqa: I001
import json
import os
import re
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings
from typing import Any
from collections.abc import Callable
from urllib.parse import urlencode


class BitrixError(Exception):
    pass


def normalize_webhook(value: str) -> str:
    value = value.strip()
    if not re.fullmatch(
        r"https://[a-z0-9-]+\.bitrix24\.(?:ru|com|by|kz|de|eu|es|fr|it|pl|com\.br)/rest/[0-9]+/[A-Za-z0-9_-]+/?",
        value,
    ):
        raise BitrixError("Указать базовый HTTPS URL входящего вебхука Bitrix24")
    return value.rstrip("/") + "/"


def cipher(create: bool = False) -> Fernet:
    path = settings.bitrix_key_path
    try:
        if create and not path.exists():
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(dir=path.parent)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(Fernet.generate_key())
                    stream.flush()
                    os.fsync(stream.fileno())
                try:
                    os.link(temporary, path)
                except FileExistsError:
                    pass
            finally:
                os.unlink(temporary)
        return Fernet(path.read_bytes())
    except (OSError, ValueError):
        raise BitrixError("Недоступен серверный ключ шифрования Bitrix24") from None


def encrypt_webhook(value: str) -> str:
    return cipher(create=True).encrypt(value.encode()).decode()


def decrypt_webhook(value: str) -> str:
    try:
        return cipher().decrypt(value.encode()).decode()
    except InvalidToken:
        raise BitrixError("Не удалось расшифровать настройки Bitrix24") from None


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        return None


class BitrixClient:
    def __init__(self, webhook: str):
        self.webhook = normalize_webhook(webhook)
        self.portal = urlsplit(self.webhook).hostname
        self.last_request = 0.0
        self.progress: Callable[[], None] = lambda: None
        self.on_progress: Callable[[str, int, int | None], None] = (
            lambda stage, completed, total: None
        )

    def call(self, method: str, params: dict) -> dict:
        for attempt in range(3):
            self.progress()
            time.sleep(max(0, 0.55 - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            request = Request(
                self.webhook + method + ".json",
                data=json.dumps(params).encode(),
                headers={"Content-Type": "application/json"},
            )
            try:
                with build_opener(NoRedirect()).open(request, timeout=25) as response:
                    raw = response.read(16 * 1024 * 1024 + 1)
                if len(raw) > 16 * 1024 * 1024:
                    raise BitrixError("Ответ Bitrix24 слишком большой")
                payload = json.loads(raw)
            except HTTPError as error:
                if error.code in (429, 500, 502, 503, 504) and attempt < 2:
                    time.sleep(2**attempt)
                    continue
                raise BitrixError(
                    f"Bitrix24: HTTP {error.code}. Проверить доступ и права вебхука"
                ) from None
            except (URLError, TimeoutError, OSError):
                if attempt < 2:
                    time.sleep(2**attempt)
                    continue
                raise BitrixError(
                    "Bitrix24 недоступен. Повторить загрузку позже"
                ) from None
            except (ValueError, TypeError):
                raise BitrixError("Bitrix24 вернул некорректный ответ") from None
            if not isinstance(payload, dict):
                raise BitrixError("Bitrix24 вернул некорректный ответ")
            error_code = payload.get("error")
            if error_code:
                if (
                    error_code in ("QUERY_LIMIT_EXCEEDED", "OPERATION_TIME_LIMIT")
                    and attempt < 2
                ):
                    time.sleep(2**attempt)
                    continue
                raise BitrixError(
                    "Bitrix24 отклонил запрос. Проверить права и доступ к REST API"
                )
            if "result" not in payload:
                raise BitrixError("В ответе Bitrix24 отсутствует результат")
            return payload
        raise BitrixError("Превышен лимит запросов Bitrix24")

    def listing(
        self, method: str, key: str | None, params: dict | None = None
    ) -> list[dict]:
        stage = {
            "catalog.catalog.list": "Загрузка списка каталогов",
            "catalog.product.list": "Загрузка товаров",
            "catalog.product.offer.list": "Загрузка вариаций товаров",
            "catalog.price.list": "Загрузка цен",
            "crm.category.list": "Загрузка воронок",
            "crm.status.list": "Загрузка стадий",
            "crm.deal.list": "Проверка ранее загруженных сделок"
            if "@ID" in (params or {}).get("filter", {})
            else "Загрузка списка открытых сделок",
        }.get(method, "Загрузка списка")
        self.on_progress(stage, 0, None)
        result: list[dict] = []
        start = 0
        for _ in range(2000):
            page = self.call(method, {**(params or {}), "start": start})
            rows = (
                page["result"]
                if key is None
                else (
                    page["result"].get(key)
                    if isinstance(page["result"], dict)
                    else None
                )
            )
            if not isinstance(rows, list) or any(
                not isinstance(row, dict) for row in rows
            ):
                raise BitrixError("Неожиданный формат списка Bitrix24")
            result.extend(rows)
            total = page.get("total")
            self.on_progress(
                stage, len(result), int(total) if total is not None else None
            )
            if "next" not in page:
                return result
            next_start = int(page["next"])
            if next_start <= start:
                raise BitrixError("Некорректная пагинация Bitrix24")
            start = next_start
        raise BitrixError("Превышен размер каталога Bitrix24")

    def snapshot(self) -> tuple[list[dict], dict]:
        catalogs = self.listing("catalog.catalog.list", "catalogs")
        items = []
        metadata = {}
        for catalog in catalogs:
            catalog_id = int(catalog["iblockId"])
            offers = bool(catalog.get("productIblockId"))
            method = "catalog.product.offer" if offers else "catalog.product"
            fields = self.call(
                method + ".getFieldsByFilter", {"filter": {"iblockId": catalog_id}}
            )["result"]
            # Название ключа зависит от типа объекта
            definitions = fields.get("offer" if offers else "product", fields)
            if not isinstance(definitions, dict) or "id" not in definitions:
                raise BitrixError("Не удалось получить описание полей товаров")
            metadata[str(catalog_id)] = {"catalog": catalog, "fields": definitions}
            rows = self.listing(
                method + ".list",
                "offers" if offers else "products",
                {
                    "select": list(definitions),
                    "filter": {"iblockId": catalog_id},
                    "order": {"id": "asc"},
                },
            )
            items.extend(rows)
        prices = self.listing("catalog.price.list", "prices")
        by_product: dict[int, list] = {}
        for price in prices:
            by_product.setdefault(int(price["productId"]), []).append(price)
        for item in items:
            item["_prices"] = by_product.get(int(item["id"]), [])

        return self.redact(items), self.redact(metadata)

    def redact(self, value: Any) -> Any:
        # Подписанные ссылки на файлы могут содержать секрет вебхука
        if isinstance(value, str):
            if self.webhook.rstrip("/").split("/")[-1] in value:
                return "[Защищённая ссылка Bitrix24]"
            return value
        if isinstance(value, list):
            return [self.redact(part) for part in value]
        if isinstance(value, dict):
            return {key: self.redact(part) for key, part in value.items()}
        return value

    def deals_snapshot(self, known_ids: list[int]) -> tuple[list[dict], dict]:
        self.on_progress("Загрузка описаний полей сделок", 0, None)
        fields = self.call("crm.deal.fields", {})["result"]
        categories = self.listing(
            "crm.category.list", "categories", {"entityTypeId": 2}
        )
        stages = []
        for category in categories:
            category_id = int(category["id"])
            entity = "DEAL_STAGE" if category_id == 0 else f"DEAL_STAGE_{category_id}"
            stages.extend(
                self.listing("crm.status.list", None, {"filter": {"ENTITY_ID": entity}})
            )
        current = self.listing(
            "crm.deal.list",
            None,
            {
                "filter": {"CLOSED": "N"},
                "select": ["ID"],
                "order": {"ID": "ASC"},
            },
        )
        identifiers = {int(row["ID"]) for row in current}
        missing = sorted(set(known_ids) - identifiers)
        for offset in range(0, len(missing), 50):
            previous = self.listing(
                "crm.deal.list",
                None,
                {
                    "filter": {"@ID": missing[offset : offset + 50]},
                    "select": ["ID"],
                    "order": {"ID": "ASC"},
                },
            )
            identifiers.update(int(row["ID"]) for row in previous)
        items = []
        ordered = sorted(identifiers)
        self.on_progress("Загрузка карточек и товаров сделок", 0, len(ordered))
        # Полная карточка содержит в том числе множественные пользовательские поля
        for offset in range(0, len(ordered), 25):
            ids = ordered[offset : offset + 25]
            commands = {}
            for identifier in ids:
                query = urlencode({"id": identifier})
                commands[f"deal_{identifier}"] = "crm.deal.get?" + query
                commands[f"rows_{identifier}"] = "crm.deal.productrows.get?" + query
            batch = self.call("batch", {"halt": 0, "cmd": commands})["result"]
            if batch.get("result_error"):
                raise BitrixError(
                    "Не удалось загрузить часть сделок. Предыдущие данные сохранены"
                )
            results = batch.get("result", {})
            for identifier in ids:
                deal = results.get(f"deal_{identifier}")
                rows = results.get(f"rows_{identifier}")
                if (
                    not isinstance(deal, dict)
                    or not isinstance(rows, list)
                    or int(deal.get("ID", 0)) != identifier
                ):
                    raise BitrixError("Неполный ответ по сделкам Bitrix24")
                items.append({"fields": deal, "product_rows": rows})
            self.on_progress(
                "Загрузка карточек и товаров сделок", len(items), len(ordered)
            )
        return self.redact(items), self.redact(
            {"fields": fields, "categories": categories, "stages": stages}
        )
