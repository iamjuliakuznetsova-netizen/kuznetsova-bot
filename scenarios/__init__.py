from . import domen, gptwork, upakovka

REGISTRY = {
    upakovka.SCENARIO["key"]: upakovka.SCENARIO,
    domen.SCENARIO["key"]: domen.SCENARIO,
    gptwork.SCENARIO["key"]: gptwork.SCENARIO,
}
