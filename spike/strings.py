"""User-visible strings. Same keys in Armenian and English. No security claims."""

STRINGS = {
    "hy": {
        "new_envelope": "նոր ծրար",
        "invite_once": "հրավերը մեկ անգամ է",
        "call_dropped": "զանգը կտրվեց. ուղիղ կապ չկա",
        "not_audited": "արտաքին աուդիտ դեռ չկա",
        "disappeared": "նամակը անհետացել է",
    },
    "en": {
        "new_envelope": "new envelope",
        "invite_once": "the invite works once",
        "call_dropped": "call dropped. no direct connection",
        "not_audited": "no external audit yet",
        "disappeared": "the letter has disappeared",
    },
}


def text(lang: str, key: str) -> str:
    return STRINGS[lang][key]
