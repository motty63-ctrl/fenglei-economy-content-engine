from fanglei.providers.document import FetchContext
from fanglei.providers.official import (
    BeaAdapter,
    ImfAdapter,
    OecdAdapter,
    OfficialSourceRouter,
    WorldBankAdapter,
)


US_2024 = FetchContext(country="USA", years=("2024",), indicators=("real_gdp_growth",), questions=())


def test_world_bank_mapping_uses_explicit_indicator_country_and_year() -> None:
    plan = WorldBankAdapter().build_plan(
        "https://data.worldbank.org/indicator/NY.GDP.MKTP.KD.ZG?locations=US",
        US_2024,
    )
    assert len(plan) == 1
    target = plan[0]
    assert target.method == "api"
    assert "/country/USA/indicator/NY.GDP.MKTP.KD.ZG" in target.url
    assert "date=2024%3A2024" in target.url
    assert target.safe_url == target.url
    assert len(target.request_fingerprint) == 64


def test_world_bank_rejects_ambiguous_country_or_year() -> None:
    adapter = WorldBankAdapter()
    no_country = "https://data.worldbank.org/indicator/NY.GDP.MKTP.KD.ZG"
    assert adapter.build_plan(no_country, US_2024) == []
    assert adapter.build_plan(
        "https://data.worldbank.org/indicator/NY.GDP.MKTP.KD.ZG?locations=US",
        FetchContext(country="USA", years=(), indicators=("real_gdp_growth",), questions=()),
    ) == []


def test_bea_only_accepts_complete_existing_api_parameters() -> None:
    adapter = BeaAdapter()
    complete = (
        "https://apps.bea.gov/api/data?DatasetName=NIPA&TableName=T10101&Year=2024&ResultFormat=JSON"
    )
    assert adapter.build_plan(complete, US_2024)[0].method == "api"
    assert adapter.build_plan("https://www.bea.gov/news/2025/gdp-release", US_2024) == []
    assert adapter.build_plan("https://apps.bea.gov/api/data?DatasetName=NIPA&Year=2024", US_2024) == []


def test_imf_requires_explicit_indicator_country_and_year() -> None:
    adapter = ImfAdapter()
    explicit = "https://www.imf.org/external/datamapper/NGDP_RPCH@WEO/USA?year=2024"
    plan = adapter.build_plan(explicit, US_2024)
    assert "/api/v1/NGDP_RPCH/USA" in plan[0].url
    assert adapter.build_plan("https://www.imf.org/external/datamapper/index.php", US_2024) == []


def test_oecd_requires_an_existing_api_data_key() -> None:
    adapter = OecdAdapter()
    explicit = "https://sdmx.oecd.org/public/rest/v1/data/OECD.SDD.NAD,DSD_NAMAIN1@DF_QNA,/.USA.B1GQ...?startPeriod=2024&endPeriod=2024"
    assert adapter.build_plan(explicit, US_2024)[0].url == explicit
    assert adapter.build_plan("https://www.oecd.org/en/data/gdp.html", US_2024) == []


def test_router_does_not_guess_when_no_adapter_has_a_certain_mapping() -> None:
    router = OfficialSourceRouter()
    assert router.plan("https://www.oecd.org/en/data/gdp.html", US_2024) == []
