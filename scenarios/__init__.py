from . import domen, gptwork, shrifty, tg_uroki, upakovka

REGISTRY = {
    upakovka.SCENARIO["key"]: upakovka.SCENARIO,
    domen.SCENARIO["key"]: domen.SCENARIO,
    gptwork.SCENARIO["key"]: gptwork.SCENARIO,
    shrifty.SCENARIO["key"]: shrifty.SCENARIO,
    tg_uroki.SCENARIO["key"]: tg_uroki.SCENARIO,
}
