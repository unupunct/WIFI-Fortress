#!/usr/bin/env python3
"""Build the ten bundled WiFi Fortress dictionary resources.

Run from the repository root:

    python scripts/build_dictionaries.py

The generator is deterministic: running it twice produces byte-identical
files.  Every entry is written by this script - nothing is downloaded or
copied from a third-party list.  The Combined dictionary is the de-duplicated
union of the other nine, in file order.

Files are UTF-8, LF line endings, one entry per line, ``#`` comments allowed.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from wififortress.resources.dictionaries.manifest import (  # noqa: E402
    DICTIONARY_SPECS,
    SPEC_BY_ID,
)

OUT_DIR = ROOT / "wififortress" / "resources" / "dictionaries"

# --------------------------------------------------------------------------
# 1. Common Passwords
# --------------------------------------------------------------------------
COMMON_PASSWORDS = """
password password1 password12 password123 password1234 password12345
passw0rd passwort passwd pass pass1 pass12
123456 1234567 12345678 123456789 1234567890 0123456789 0987654321
12345 1234 111111 000000 121212 654321 123123 112233 131313 151515
abc123 abc1234 abcd1234 a1b2c3 aaa111 1q2w3e4r 1q2w3e4r5t 1qaz2wsx 1qaz2wsx3edc
qwerty qwerty1 qwerty12 qwerty123 qwerty1234 qwertyuiop qwertz qwertz123 azerty
asdf asdf123 asdfgh asdfghjkl zxcvbnm zxcvbnm123 poiuytrewq
letmein letmein1 letmein123 welcome welcome1 welcome123 welcome2024
admin admin1 admin12 admin123 admin1234 administrator root toor
iloveyou iloveyou1 iloveyou2 monkey monkey1 dragon dragon1
sunshine princess princess1 football baseball basketball soccer
superman batman starwars pokemon minecraft naruto
shadow master master1 michael jennifer jordan hunter killer
trustno1 whatever nothing secret secret1 mysecret
login guest default changeme changeit test test1 test123 testing
temp password! Password1 Password123 Passw0rd! P@ssw0rd P@ssw0rd!
Password@123 Admin@123 Welcome@123 Qwerty@123
letmein! iloveyou! welcome! admin123!
summer winter spring autumn january february december
freedom flower hello hello123 helloworld hellothere
company office office123 work work123
linkedin facebook google twitter instagram youtube tiktok
samsung iphone android windows linux ubuntu parrot kali
internet wifi wlan router network wireless
myspace1999 blinker trustno1 qazwsx qazwsxedc
0000 1111 2222 3333 4444 5555 6666 7777 8888 9999
12341234 12344321 123321 11111111 22222222 87654321
2020 2021 2022 2023 2024 2025 2026 2019 2018 2017
password01 password02 password2024 password2025 password2026
changeme123 changeme! default123
hunter2 hunter12 superman1 batman1
access access1 access123 enter enter123
god god1 jesus love lover lovely honey honey123 baby babygirl
killer123 matrix neo morpheus trinity
zaq12wsx xsw21qaz 1qazxsw2 qwe123 qweasd qweasdzxc
passion football1 soccer1 hockey1 tennis1 golfer
monkey123 dragon123 sunshine1 princess123
steelers cowboys yankees lakers
q1w2e3r4 q1w2e3r4t5 a1s2d3f4 z1x2c3v4
iloveu iloveyou3
opensesame sesame sesame123
!@#$%^&* 1q2w3e 123qwe qweasdzxc123
administrator123 adminadmin superadmin sysadmin
support support1 helpdesk
demo demo123 sample sample123
qwertyui qwertyui1
passwordpassword passwordpass
azerty123 azertyuiop
omega alpha bravo charlie delta
starwars1 startrek1
""".strip().split()

# --------------------------------------------------------------------------
# 2. English Words
# --------------------------------------------------------------------------
ENGLISH_WORDS = """
about above accept access account across action active actor adapt add address
admit adult advance advice affect after again against age agency agent agree air
all allow almost alone along already also always among amount analysis animal
answer anyone anything appear apply area argue arm around arrive art article
artist assume attack attention author available avoid away baby back bad bag ball
bank bar base basic battery beach bear beat beautiful because become bed before
begin behavior behind believe below best better between beyond big bill bird
birth black blue board boat body book born both box boy break bring brother
budget build bus business buy call camera campaign can candidate capital car card
care career carry case catch cause cell center central century certain chair
challenge chance change character charge check child choice choose church city
civil claim class clear client close coach cold collection college color come
commercial common community company compare computer concern condition conference
consider consumer contain continue control cost could country couple course court
cover create crime cultural culture cup current customer cut dark data daughter
day dead deal death debate decade decide decision deep defense degree describe
design despite detail determine develop die difference difficult dinner
direction director discover discuss disease doctor door down draw dream drive
drop drug during each early east easy eat economic economy edge education effect
effort eight either election else employee end energy enjoy enough enter entire
environment especially establish even evening event ever every everyone
everything evidence exactly example executive exist expect experience expert
explain eye face fact factor fail fall family far fast father fear federal feel
feeling few field fight figure fill film final finally financial find fine finger
finish fire firm first fish five floor fly focus follow food foot force foreign
forget form former forward four free friend from front full fund future game
garden general generation get girl give glass go goal good government great green
ground group grow growth guess gun guy hair half hand hang happen happy hard have
head health hear heart heat heavy help her here herself high him himself history
hit hold home hope hospital hot hotel hour house how however huge human hundred
husband idea identify if image imagine impact important improve in include
including increase indeed indicate individual industry information inside
instead institution interest international interview into investment involve
issue item its itself job join just keep key kid kill kind kitchen know knowledge
land language large last late later laugh law lawyer lay lead leader learn least
leave left leg legal less let letter level lie life light like likely line list
listen little live local long look lose loss lot love low machine magazine main
maintain major majority make man manage management manager many market marriage
material matter may maybe me mean measure media medical meet meeting member
memory mention message method middle might military million mind minute miss
mission model modern moment money month more morning most mother mouth move
movement movie much music must my myself name nation national natural nature near
nearly necessary need network never new news newspaper next nice night no none
nor north not note nothing notice now number occur off offer office officer
official often oil ok old on once one only onto open operation opportunity
option or order organization other others our out outside over own owner page
pain painting paper parent part participant particular particularly partner
party pass past patient pattern pay peace people per perform performance perhaps
period person personal phone pick picture piece place plan plant play player pm
point police policy political politics poor popular population position positive
possible power practice prepare present president pressure pretty prevent price
private probably problem process produce product production professional program
project property protect prove provide public pull purpose push put quality
question quickly quite race radio raise range rate rather reach read ready real
reality realize really reason receive recent recently recognize record red reduce
reflect region relate relationship religious remain remember remove report
represent require research resource respond response responsibility rest result
return reveal rich right rise risk road rock role room rule run safe same save say
scene school science score sea season seat second section security see seek seem
sell send senior sense series serious serve service set seven several shake share
she shoot short should shoulder show side sign significant similar simple simply
since sing single sister sit site situation six size skill skin small smile so
social society soldier some somebody someone something sometimes son song soon
sort sound source south space speak special specific speech spend sport spring
staff stage stand standard star start state statement station stay step still
stock stop store story strategy street strong structure student study stuff style
subject success successful such suddenly suffer suggest summer support sure
surface system table take talk task tax teach teacher team technology television
tell ten tend term test than thank that the their them themselves then theory
there these they thing think third this those though thought thousand threat
three through throughout throw thus time to today together tonight too top total
tough toward town trade traditional training travel treat treatment tree trial
trip trouble true truth try turn two type under understand unit until up upon us
use usually value various very victim view violence visit voice vote wait walk
wall want war watch water way weapon wear week weight well west what whatever
when where whether which while white who whole whom whose why wide wife will win
wind window wish with within without woman wonder word work worker world worry
would write writer wrong yard yeah year yes yet you young your yourself
apple orange banana cherry grape lemon melon peach pear plum strawberry
coffee tea juice milk bread cheese butter sugar honey salt pepper
dog cat horse tiger lion eagle shark wolf bear rabbit mouse duck goose
summer winter autumn spring rainbow thunder storm cloud river ocean mountain
guitar piano violin drum music dance painting drawing poetry novel
freedom justice honor courage wisdom patience loyalty kindness honesty
password secret key lock unlock shield fortress castle dragon knight
computer laptop keyboard monitor printer network wireless internet
""".strip().split()

# --------------------------------------------------------------------------
# 3. Romanian Words (with diacritics, plus unaccented spellings)
# --------------------------------------------------------------------------
ROMANIAN_WORDS = """
si sa nu da la cu pe de din in prin pentru fara dupa despre intre catre spre
eu tu el ea noi voi ei ele mine tine sine nou vostru lor
este sunt era fost fi fie avea are avem aveti au
face faci facem faceti fac merge mergi vine vin stiu stii stie vreau vrei
pot poti poate putem puteti trebuie vrea vreau
mare mic bun rau frumos urat nou vechi lung scurt inalt jos greu usor
cald rece fierbinte rapid lent puternic slab bogat sarac fericit trist
om oameni femeie barbat copil copii familie mama tata frate sora fiu fiica
bunic bunica prieten prieteni vecin vecini coleg sef
casa apartament camera bucatarie baie dormitor usa fereastra pat masa scaun
birou calculator telefon televizor masina bicicleta tren avion autobuz
strada oras sat tara lume pamant cer soare luna stea stele nor ploaie
zapada vant cald frig iarna vara primavara toamna zi noapte dimineata seara
apa foc aer pamant lemn piatra fier aur argint metal sticla hartie
mancare paine branza lapte carne oua fructe legume mere pere prune
cafea ceai suc vin bere miere zahar sare piper
munte muntele mare marea rau lac padure copac copaci floare flori iarba
animal caine pisica cal vaca porc gaina peste pasare urs lup vulpe iepure
rosu albastru verde galben negru alb gri roz mov portocaliu maro
unu doi trei patru cinci sase sapte opt noua zece douazeci suta mie
luni marti miercuri joi vineri sambata duminica
ianuarie februarie martie aprilie mai iunie iulie august septembrie
octombrie noiembrie decembrie
dragoste iubire prietenie fericire bucurie tristete frica curaj speranta
liniste pace razboi viata moarte sanatate boala doctor spital medicament
scoala profesor elev student lectie carte caiet creion stilou
lucru serviciu bani salariu pret ieftin scump magazin piata cumparare
munca odihna vacanta calatorie drum drumul casa acasa departe aproape
bine rau mult putin tot nimic ceva cineva nimeni oriunde niciodata mereu
azi maine ieri acum atunci cand unde cum de ce care cine ce
salut buna bunaseara noaptebuna la revedere multumesc scuze te rog
bun venit ajutor ajuta sprijin sigur siguranta protectie parola
cheie lacat usa intrare iesire deschis inchis liber ocupat
wifi retea internet semnal conexiune router modem cablu
romania roman romaneste limba cuvant cuvinte propozitie
mama tata copilul baiat fata domn doamna domnisoara
ani anul luna saptamana ora minut secunda timp vreme
salutare ce faci sunt bine multam
""".strip().split()

# --------------------------------------------------------------------------
# 4. Numeric Patterns
# --------------------------------------------------------------------------
NUMERIC_PATTERNS = [
    *[str(n) for n in range(0, 100)],
    *[f"{n:02d}" for n in range(0, 100)],
    *[str(y) for y in range(1950, 2036)],
    *[f"{d:02d}{m:02d}" for m in range(1, 13) for d in range(1, 29)],
    *[f"{d:02d}{m:02d}{y}" for y in (1990, 1995, 2000) for m in range(1, 13) for d in (1, 2, 3, 15, 20)],
    "123", "1234", "12345", "123456", "1234567", "12345678", "123456789",
    "1234567890", "0123456789", "9876543210", "987654321", "87654321",
    "111111", "222222", "333333", "444444", "555555", "666666", "777777",
    "888888", "999999", "000000", "11111111", "00000000", "123123", "321321",
    "112233", "121212", "101010", "131313", "141414", "151515", "161616",
    "171717", "181818", "191919", "202020", "212121", "232323", "242424",
    "252525", "010101", "13579", "24680", "135790", "02468", "112358",
    "314159", "271828", "8675309", "007", "911", "112", "999", "100", "1000",
    "10000", "100000", "69", "420", "777", "888", "666", "123321", "456789",
    "654321", "147258", "2580", "741852963", "159753", "753951", "951753",
    "1234abcd", "0000", "1111", "2222", "3333", "4444", "5555", "6666",
    "7777", "8888", "9999", "12", "21", "01", "02", "03", "07", "10",
    "2000", "2001", "2002", "2003", "2004", "2005", "2006", "2007",
]

# --------------------------------------------------------------------------
# 5. Keyboard Patterns
# --------------------------------------------------------------------------
KEYBOARD_PATTERNS = """
qwerty qwertyuiop qwertyui qwertyu qwert qwer qwe qw qwertz qwertzuiop
azerty azertyuiop asdf asdfg asdfgh asdfghjkl asdfghjk zxcv zxcvb
zxcvbn zxcvbnm zxc zx xcv xcvb xc vb nm
1234qwer 12345qwert qwerty1234 qwer1234 qwe123 qweasd qweasdzxc qweasdzx
1qaz 2wsx 3edc 4rfv 5tgb 6yhn 7ujm 8ik 9ol 0p
1qaz2wsx 1qaz2wsx3edc 1qaz2wsx3edc4rfv 1qazxsw2 2wsx3edc
qazwsx qazwsxedc qazwsxedcrfv qazwsx123 qazwsxedc123
zaq12wsx zaq1zaq1 xsw21qaz xsw2cde3
q1w2e3 q1w2e3r4 q1w2e3r4t5 q1w2e3r4t5y6 a1s2d3 a1s2d3f4 a1s2d3f4g5
z1x2c3 z1x2c3v4 z1x2c3v4b5
1234asdf 1234qwer 1234qwert 4321fdsa
qweqwe qweqwe123 asdasd asdasd123 zxczxc poipoi
poiuytrewq lkjhgfdsa mnbvcxz
qaz qwe asd zxc qweqwe
plokij plokijuh mju7 mju8 nji9
QWERTY QWERTYUIOP Qwerty Qwerty123 ASDFGHJKL Asdfghjkl ZXCVBNM
Qwerty1 Qwerty12 Qwerty123 Qwerty! QWERTY123 QWERTY!
qwerty! qwerty@ qwerty# qwerty$
1q2w3e4r 1q2w3e4r5t6y7u8i9o0p 1q2w3e 1q2w 12qwaszx
qweasdzxc123 asdfghjkl123 zxcvbnm123
qwertyqwerty asdfasdf zxcvzxcv
qwertz123 Qwertz QWERTZ
""".strip().split()

# --------------------------------------------------------------------------
# 6. Common Substitutions
# --------------------------------------------------------------------------
COMMON_SUBSTITUTIONS = """
a=4 a=@ e=3 e=€ i=1 i=! o=0 o=() s=5 s=$ s=z t=7 t=+ l=1 l=| g=9 g=6 b=8
A=4 E=3 I=1 O=0 S=5 T=7
password=p@ssw0rd password=p@ssword password=pa55word password=p4ssw0rd
password=passw0rd password=pa$$word password=p@$$w0rd password=p455w0rd
admin=@dmin admin=4dmin love=l0ve love=luv money=m0ney money=money
hello=h3llo hello=h3110 hello=#3ll0 secret=s3cret secret=$ecret
test=t3st master=m4ster master=m@ster michael=m1chael
welcome=w3lc0me welcome=welcome! internet=1nternet
security=s3curity security=$ecurity system=$y$tem
iloveyou=1l0veyou iloveyou=1luvu football=f00tball
soccer=$occer dragon=dr4g0n monkey=m0nkey
samsung=$amsung google=g00gle google=g00g1e
password=Pa$$w0rd password=P@ssw0rd123
to=2 to=two for=4 you=u you=ya and=& are=r be=b
""".strip().split()

# --------------------------------------------------------------------------
# 7. Names and Dates
# --------------------------------------------------------------------------
NAMES_DATES = """
alex alexandru alexandra andrei andreea andrian ana anca anton bogdan
catalin catalina cristian cristina cosmin cornel dan daniel daniela diana
doru dragos elena emil florin gabriel george georgiana horea ion ionel ionut
irina iulian laurentiu liviu luca lucian madalina maria marius mihai mihaela
nicoleta oana ovidiu paul petre radu razvan robert romina serban sorin
stefan stefania teodor vasile victor vlad
john james robert michael william david richard joseph thomas charles
christopher daniel matthew anthony donald mark paul steven andrew kenneth
joshua kevin brian george edward ronald timothy jason jeffrey ryan jacob
gary nicholas eric jonathan stephen larry justin scott brandon benjamin
samuel gregory alexander patrick frank raymond jack dennis jerry tyler
mary patricia jennifer linda elizabeth barbara susan jessica sarah karen
nancy lisa betty margaret sandra ashley kimberly emily donna michelle carol
amanda dorothy melissa deborah stephanie rebecca sharon laura cynthia kathleen
amy angela shirley anna brenda pamela emma nicole helen samantha katherine
christine debra rachel carolyn janet catherine heather diane ruth julie
olivia joyce virginia victoria kelly lauren christina joan evelyn
smith johnson williams brown jones garcia miller davis rodriguez martinez
hernandez lopez gonzalez wilson anderson thomas taylor moore jackson martin
lee perez thompson white harris sanchez clark ramirez lewis robinson walker
young allen king wright scott torres nguyen hill flores green adams nelson
baker hall rivera campbell mitchell carter roberts gomez phillips evans
turner diaz parker cruz edwards collins reyes stewart morris morales murphy
cook rogers gutierrez ortiz morgan cooper peterson bailey reed kelly howard
ramos kim cox ward richardson watson brooks chavez wood james bennett gray
mendoza ruiz hughes price alvarez castillo sanders patel myers long ross
foster jimenez powell jenkins perry russell sullivan bell coleman butler
henderson barnes gonzales fisher vasquez simmons romero jordan patterson
alexander hamilton graham reynolds griffin wallace moreno west cole hayes
bryant herrera gibson ellis tran medina aguilar stevens murray ford castro
marshall owens harrison fernandez mcdonald woods washington kennedy wells
popa popescu ionescu radulescu dumitru stoica georgescu marin tudor
moldovan matei constantin nistor barbu savu toader munteanu
""".strip().split() + [
    *[f"{n}{y}" for n in ("alex", "maria", "andrei", "dan", "john", "anna")
      for y in ("1990", "1995", "2000", "2005", "2010")],
    *[f"{y}" for y in range(1960, 2026)],
    *[f"{d:02d}.{m:02d}.{y}" for y in (1985, 1990, 1995, 2000, 2005) for m in (1, 6, 12) for d in (1, 15, 25)],
    *[f"{d:02d}-{m:02d}-{y}" for y in (1990, 2000) for m in (1, 6, 12) for d in (1, 15, 25)],
    *[f"{d:02d}/{m:02d}/{y}" for y in (1990, 2000) for m in (1, 6, 12) for d in (1, 15, 25)],
]

# --------------------------------------------------------------------------
# 8. Short Passphrases
# --------------------------------------------------------------------------
SHORT_PASSPHRASES = """
iloveyou loveyou loveme loveu loveu2 loveme2 trustme trustnoone
letmein letmeinplease openthedoor opensesame
helloworld hellothere helloeveryone bye bye123 goodmorning goodnight
goodluck goodday goodlife goodboy goodgirl
thankyou thanks please sorry welcome back home
mypassword mysecret mylife myworld mylove myheart myfamily myhome
mydog mycat mykids mywife myhusband mybaby myfriend
secretkey secretpass topsecret supersecret
donttell dontforget dontworry dontstop
nothinghere nothing123 nobodyknows
sunshine1 sunrise sunset moonlight starlight
blackwhite redgreen blueblue
catdog catmouse blackcat whitecat
happyday happyface happylife happiness
summer2024 summer2025 winter2024 winter2025 spring2024 autumn2024
newyork losangeles lasvegas sanfrancisco
computer123 internet1 facebook1 twitter1
football1 baseball1 basketball1
letmeinnow accessnow loginnow
onetwothree one2three one-two-three
abc123def abcdefgh
dearfriend bestfriend girlfriend boyfriend
""".strip().split()

# --------------------------------------------------------------------------
# 9. Extended Password Patterns
# --------------------------------------------------------------------------
_EXT_BASES = [
    "password", "admin", "welcome", "letmein", "secret", "qwerty",
    "iloveyou", "monkey", "dragon", "summer", "winter", "football",
    "soccer", "princess", "sunshine", "master", "shadow", "superman",
    "batman", "hello", "test", "guest", "login", "user", "root",
    "love", "money", "family", "house", "office", "company", "internet",
    "wifi", "router", "network", "samsung", "google", "apple", "microsoft",
    "windows", "linux", "parrot", "romania", "bucuresti",
]
_EXT_SUFFIXES = [
    "1", "12", "123", "1234", "12345", "123456", "01", "001", "007",
    "2020", "2021", "2022", "2023", "2024", "2025", "2026",
    "!", "!!", "!!!", "!1", "!123", "@123", "#123", "$123", "123!",
    "@", "#", "$", "*", "69", "99", "88", "777", "666",
]
_EXT_PREFIXES = ["1", "123", "!", "@", "#", "$", "my", "the", "super", "its"]
_EXT_INFIX = ["_", "-", ".", "@", ""]

EXTENDED_PATTERNS: list[str] = []
for _base in _EXT_BASES:
    EXTENDED_PATTERNS.append(_base)
    for _suffix in _EXT_SUFFIXES:
        EXTENDED_PATTERNS.append(f"{_base}{_suffix}")
    for _prefix in _EXT_PREFIXES:
        EXTENDED_PATTERNS.append(f"{_prefix}{_base}")
    for _sep in ("_", "-", "."):
        for _suffix in ("123", "2024", "2025"):
            EXTENDED_PATTERNS.append(f"{_base}{_sep}{_suffix}")
EXTENDED_PATTERNS += [
    "p@ssw0rd", "P@ssw0rd", "P@ssw0rd!", "Pa$$w0rd", "Pa$$word",
    "P4ssw0rd", "P455w0rd", "Adm1n", "Adm1n123", "Welc0me", "W3lc0me",
    "L3tm31n", "S3cr3t", "S3cr3t123", "M0nkey", "Dr4gon", "Sunsh1ne",
]

# --------------------------------------------------------------------------
# 3b. Romanian Words with correct diacritics (UTF-8)
# --------------------------------------------------------------------------
# The same vocabulary written with the characters Romanian actually uses.
# Both spellings are kept: people type "parola" and "parolă".
ROMANIAN_DIACRITICS = """
și să nu dă la cu pe de din în prin pentru fără după despre între către spre
eu tu el ea noi voi ei ele mine ție sine nou vostru lor
este sînt sunt era fost fii fie avea are avem aveți au
face faci facem faceți fă merge mergi vine vin știu știi știe vreau vrei
pot poți poate putem puteți trebuie vrea
mare mic bun rău frumos urît nou vechi lung scurt înalt jos greu ușor
cald rece fierbinte rapid lent puternic slab bogat sărac fericit trist
om oameni femeie bărbat copil copii familie mamă tată frate soră fiu fiică
bunic bunică prieten prieteni vecin vecini coleg șef
casă apartament cameră bucătărie baie dormitor ușă fereastră pat masă scaun
birou calculator telefon televizor mașină bicicletă tren avion autobuz
stradă oraș sat țară lume pămînt cer soare lună stea stele nor ploaie
zăpadă vînt cald frig iarnă vară primăvară toamnă zi noapte dimineață seară
apă foc aer pămînt lemn piatră fier aur argint metal sticlă hîrtie
mîncare pîine brînză lapte carne ouă fructe legume mere pere prune
cafea ceai suc vin bere miere zahăr sare piper
munte marea rîu lac pădure copac copaci floare flori iarbă
animal cîine pisică cal vacă porc găină pește pasăre urs lup vulpe iepure
roșu albastru verde galben negru alb gri roz mov portocaliu maro
unu doi trei patru cinci șase șapte opt nouă zece douăzeci sută mie
luni marți miercuri joi vineri sîmbătă duminică
ianuarie februarie martie aprilie mai iunie iulie august septembrie
octombrie noiembrie decembrie
dragoste iubire prietenie fericire bucurie tristețe frică curaj speranță
liniște pace război viață moarte sănătate boală doctor spital medicament
școală profesor elev student lecție carte caiet creion stilou
lucru serviciu bani salariu preț ieftin scump magazin piață cumpărare
muncă odihnă vacanță călătorie drum acasă departe aproape
bine rău mult puțin tot nimic ceva cineva nimeni oriunde niciodată mereu
azi mîine ieri acum atunci cînd unde cum de ce care cine ce
salut bună bunăseara noaptebună la revedere mulțumesc scuze te rog
bun venit ajutor ajută sprijin sigur siguranță protecție parolă
cheie lacăt ușă intrare ieșire deschis închis liber ocupat
wifi rețea internet semnal conexiune router modem cablu
românia român românește limbă cuvînt cuvinte propoziție
mamă tată copilul băiat fată domn doamnă domnișoară
ani anul lună săptămînă oră minut secundă timp vreme
salutare ce faci sunt bine mulțam
""".strip().split()

# --------------------------------------------------------------------------
# Data mapping
# --------------------------------------------------------------------------
DATA: dict[str, list[str]] = {
    "common_passwords": COMMON_PASSWORDS,
    "english_words": ENGLISH_WORDS,
    "romanian_words": ROMANIAN_WORDS + ROMANIAN_DIACRITICS,
    "numeric_patterns": NUMERIC_PATTERNS,
    "keyboard_patterns": KEYBOARD_PATTERNS,
    "common_substitutions": COMMON_SUBSTITUTIONS,
    "names_dates": NAMES_DATES,
    "short_passphrases": SHORT_PASSPHRASES,
    "extended_patterns": EXTENDED_PATTERNS,
}

HEADER = (
    "# {name}\n"
    "# {description}\n"
    "# License: {license} - {provenance}\n"
    "# One entry per line, UTF-8. Generated by scripts/build_dictionaries.py\n"
)


def dedupe_keep_order(entries: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for entry in entries:
        entry = entry.strip()
        if not entry or entry.startswith("#"):
            continue
        key = entry.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(entry)
    return out


def build() -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for dict_id, entries in DATA.items():
        result[dict_id] = dedupe_keep_order(entries)
    combined: list[str] = []
    for dict_id in DATA:
        combined.extend(result[dict_id])
    result["combined"] = dedupe_keep_order(combined)
    return result


def write_files() -> dict[str, int]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    built = build()
    counts: dict[str, int] = {}
    for spec in DICTIONARY_SPECS:
        entries = built[spec.dict_id]
        path = OUT_DIR / spec.filename
        header = HEADER.format(
            name=spec.name,
            description=spec.description.replace("\n", " "),
            license=spec.license,
            provenance=spec.provenance,
        )
        body = "\n".join(entries) + "\n"
        path.write_text(header + body, encoding="utf-8", newline="\n")
        counts[spec.dict_id] = len(entries)
        print(f"{spec.filename:32s} {len(entries):6d} entries  {path.stat().st_size:8d} bytes")
    return counts


if __name__ == "__main__":
    write_files()
