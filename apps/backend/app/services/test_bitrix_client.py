# ruff: noqa: I001
import pytest

from app.services.bitrix_client import BitrixClient, BitrixError, normalize_webhook


def test_snapshot_pages_properties_prices_and_secret_redaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Проверяем разбор ответов API на контролируемых примерах:
    - объединить страницы, получить динамические поля и цены отдельно
    - сохранить связь вариации с родителем
    - скрыть секретные ссылки в данных
    """
    calls = []

    def call(self, method, params):
        calls.append((method, params))
        if method == "catalog.catalog.list":
            return {
                "result": {
                    "catalogs": [
                        {"iblockId": 23},
                        {"iblockId": 25, "productIblockId": 23},
                    ]
                }
            }
        if method.endswith("getFieldsByFilter"):
            kind = "offer" if ".offer." in method else "product"
            return {
                "result": {
                    kind: {
                        "id": {},
                        "iblockId": {},
                        "name": {},
                        "property349": {},
                        "parentId": {},
                    }
                }
            }
        if method == "catalog.product.list":
            assert "property349" in params["select"]
            if params["start"] == 0:
                return {
                    "result": {
                        "products": [
                            {
                                "id": 1,
                                "iblockId": 23,
                                "name": "Товар",
                                "property349": {"value": "Свойство"},
                            }
                        ]
                    },
                    "next": 50,
                }
            return {"result": {"products": [{"id": 2, "iblockId": 23}]}}
        if method == "catalog.product.offer.list":
            return {
                "result": {
                    "offers": [
                        {
                            "id": 3,
                            "iblockId": 25,
                            "parentId": {"value": "1"},
                            "previewPicture": {"url": self.webhook + "download"},
                        }
                    ]
                }
            }
        if method == "catalog.price.list":
            return {
                "result": {
                    "prices": [
                        {"id": 9, "productId": 3, "price": "12.34", "currency": "RUB"}
                    ]
                }
            }
        raise AssertionError(method)

    monkeypatch.setattr(BitrixClient, "call", call)
    items, metadata = BitrixClient(
        "https://example.bitrix24.ru/rest/1/test-secret/"
    ).snapshot()
    assert [item["id"] for item in items] == [1, 2, 3]
    assert items[0]["property349"]["value"] == "Свойство"
    assert items[2]["parentId"]["value"] == "1"
    assert items[2]["_prices"][0]["price"] == "12.34"
    assert "test-secret" not in str(items)
    assert "property349" in metadata["23"]["fields"]


@pytest.mark.parametrize(
    "url",
    [
        "http://example.bitrix24.ru/rest/1/secret/",
        "https://127.0.0.1/rest/1/secret/",
        "https://example.bitrix24.ru.evil.com/rest/1/secret/",
        "https://example.bitrix24.comXbr/rest/1/secret/",
        "https://example.bitrix24.ru/rest/1/secret/?next=anything",
    ],
)
def test_webhook_rejects_untrusted_urls(url: str) -> None:
    """
    Проверяем ограничения адреса подключения:
    - отклонить локальные адреса, подмену домена и параметры URL
    - не включать секрет в текст ошибки
    """
    with pytest.raises(BitrixError) as error:
        normalize_webhook(url)
    assert "secret" not in str(error.value)


@pytest.mark.parametrize("batch_error", [False, True])
def test_deals_pages_closed_custom_fields_and_batch_failure(
    monkeypatch: pytest.MonkeyPatch, batch_error: bool
) -> None:
    """
    Проверяем загрузку на контролируемых ответах API:
    - объединить страницы открытых сделок и ранее загруженные закрытые сделки
    - сохранить множественные поля и товары, скрыть секретные ссылки
    - отклонить неполный пакет ответов
    """

    def call(self, method, params):
        if method == "crm.deal.fields":
            return {"result": {"UF_MULTI": {"formLabel": "Варианты"}}}
        if method == "crm.category.list":
            return {"result": {"categories": [{"id": 0}, {"id": 2}]}}
        if method == "crm.status.list":
            return {
                "result": [
                    {"ENTITY_ID": params["filter"]["ENTITY_ID"], "NAME": "Стадия"}
                ]
            }
        if method == "crm.deal.list":
            if "@ID" in params["filter"]:
                assert params["filter"]["@ID"] == [3, 4]
                return {"result": [{"ID": "3"}]}
            assert params["filter"] == {"CLOSED": "N"}
            return (
                {"result": [{"ID": "1"}], "next": 50}
                if params["start"] == 0
                else {"result": [{"ID": "2"}]}
            )
        if method == "batch":
            result = {}
            for key in params["cmd"]:
                identifier = key.split("_")[1]
                result[key] = (
                    {
                        "ID": identifier,
                        "CLOSED": "Y" if identifier == "3" else "N",
                        "UF_MULTI": ["a", "b"],
                        "FILE": self.webhook + "file",
                    }
                    if key.startswith("deal_")
                    else [{"ID": identifier, "QUANTITY": 2, "PRICE": 123}]
                )
            return {
                "result": {
                    "result": result,
                    "result_error": {"rows_3": {"error": "denied"}}
                    if batch_error
                    else {},
                }
            }
        raise AssertionError(method)

    monkeypatch.setattr(BitrixClient, "call", call)
    client = BitrixClient("https://example.bitrix24.ru/rest/1/test-secret/")
    if batch_error:
        with pytest.raises(BitrixError):
            client.deals_snapshot([1, 3, 4])
        return
    items, metadata = client.deals_snapshot([1, 3, 4])
    assert [item["fields"]["ID"] for item in items] == ["1", "2", "3"]
    assert items[2]["fields"]["CLOSED"] == "Y"
    assert items[0]["fields"]["UF_MULTI"] == ["a", "b"]
    assert items[1]["product_rows"][0]["PRICE"] == 123
    assert "test-secret" not in str(items)
    assert [stage["ENTITY_ID"] for stage in metadata["stages"]] == [
        "DEAL_STAGE",
        "DEAL_STAGE_2",
    ]


def test_listing_reports_page_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Проверяем прогресс страниц:
    - сообщить количество полученных элементов после каждой страницы
    - использовать общий размер списка из ответа API
    """
    client = BitrixClient("https://example.bitrix24.ru/rest/1/test-secret/")
    events = []
    client.on_progress = lambda stage, count, total: events.append(
        (stage, count, total)
    )
    monkeypatch.setattr(
        client,
        "call",
        lambda method, params: (
            {"result": [{"ID": 1}], "total": 2, "next": 50}
            if params["start"] == 0
            else {"result": [{"ID": 2}], "total": 2}
        ),
    )
    rows = client.listing("crm.deal.list", None, {"filter": {"CLOSED": "N"}})
    assert len(rows) == 2
    assert [(count, total) for _, count, total in events] == [(0, None), (1, 2), (2, 2)]
