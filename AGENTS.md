# Anun — գործակալի կանոններ

Կարդա `PLAN.md` և `README.md` նախքան կոդ գրելը։

- Ռելեն կույր է։ `spike/relay.py`-ում չկա և չպետք է լինի decrypt, private key, կամ AES։
- Սեփական ծածկագիր արգելված է։ Միայն `cryptography` կամ նույն դասի ստուգված գրադարան։
- Հեռախոսահամար, էլփոստ, գլոբալ user id — արգելված։
- «Աշխարհի ամենաանվտանգը» և «100%» արգելված են փաստաթղթում, քանի դեռ արտաքին աուդիտ չկա։
- Զանգը, երբ գա, ուղիղ IP չի բացում։ Եթե ռելեն ընկել է, ուղիղ կապի վրա մի անցիր։
- SimpleX կոդ չպատճենել (AGPL)։
- Թեստն անցկացրու նախքան push. `python3 -m unittest spike.test_spike spike.test_phase3 spike.test_continue spike.test_product spike.test_reply spike.test_file_parts spike.test_disappear spike.test_opus spike.test_call_run`
