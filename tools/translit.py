# -*- coding: utf-8 -*-
"""Обратный транслит имён Базиса: «Bokovina_levaya» -> «Боковина левая».

Базис заменяет любой не-буквенный символ (пробел, ь, скобку, запятую) на «_»,
поэтому восстановление эвристическое: мягкий знак ставится по типичным
окончаниям, скобки — по шаблону «Слово__пояснение_число_».
"""
import re

# латиница, которую не переводим (бренды, артикулы, английские слова)
KEEP = {
    'steel', 'seal', 'clip', 'top', 'blumotion', 'asko', 'blum', 'hettich', 'boyard',
    'tandembox', 'legrabox', 'movento', 'aventos', 'servo', 'drive', 'tip', 'on', 'push',
    'egger', 'kronospan', 'open', 'gravika', 'minifix', 'lamarty', 'gtv', 'hafele', 'bosch', 'gorenje', 'beko', 'maunfeld',
    'pe', 'led',
}
# слова, после которых «_» = мягкий знак (+ пробел)
SOFT = {'dver', 'mebel', 'stal', 'panel', 'shchel', 'antresol', 'tsokol', 'profil',
        'rel', 'kol', 'fil', 'stiral', 'sushil', 'gladil', 'pereklyuchatel', 'vyklyuchatel',
        'ogranichitel', 'dovodchik', 'derzhatel', 'polotentse', 'bel', 'nakladnaya'}
NOT_SOFT = {'stol', 'ugol', 'pol', 'nakladnaya', 'nad', 'pod'}
SHORT_WORDS = {'i', 'v', 'na', 's', 'k', 'u', 'o', 'ot', 'do', 'po', 'za', 'iz', 'pod', 'nad',
               'dlya', 'bez', 'pri', 'ili', 'mm', 'sm', 'sht', 'na', 'so', 've', 'vo', 'ne'}
STRONG = ('naya', 'nyy', 'noe', 'nye', 'nykh', 'nogo', 'nuyu', 'nym', 'nyye', 'nymi', 'noy')
SUFFIX_SOFT = ('naya', 'nyy', 'noe', 'nye', 'nykh', 'nogo', 'nuyu', 'nym', 'nyj', 'yo', 'ya',
               'ye', 'yu', 'e', 'tso', 'tsa', 'tra', 'ka', 'ki', 'ko', 'ny')

PAIRS = [('shch', 'щ'), ('sh', 'ш'), ('ch', 'ч'), ('zh', 'ж'), ('kh', 'х'), ('ts', 'ц'),
         ('yo', 'ё'), ('yu', 'ю'), ('ya', 'я')]
SINGLE = {'a': 'а', 'b': 'б', 'v': 'в', 'g': 'г', 'd': 'д', 'e': 'е', 'z': 'з', 'i': 'и',
          'k': 'к', 'l': 'л', 'm': 'м', 'n': 'н', 'o': 'о', 'p': 'п', 'r': 'р', 's': 'с',
          't': 'т', 'u': 'у', 'f': 'ф', 'h': 'х', 'j': 'й', 'c': 'ц', 'w': 'в', 'x': 'кс', 'q': 'к'}
VOWELS_RU = set('аеёиоуыэюяй')
CONS_LAT = set('bcdfghjklmnpqrstvwxz')


def _is_latin_keep(w):
    lw = w.lower()
    if lw in KEEP:
        return True
    if len(w) >= 2 and w.isupper():
        return True
    if any(ch.isdigit() for ch in w):
        return True
    if re.search(r'[wqx]|c(?!h)', lw):
        return True
    return False


def word(w):
    """Один латинский токен -> кириллица."""
    if _is_latin_keep(w):
        return w
    lw = w.lower()
    out = []
    i = 0
    while i < len(lw):
        for lat, ru in PAIRS:
            if lw.startswith(lat, i):
                out.append(ru)
                i += len(lat)
                break
        else:
            ch = lw[i]
            if ch == 'y':
                prev = out[-1][-1] if out else ''
                out.append('й' if (prev in VOWELS_RU or prev == 'ы' or not prev) else 'ы')
            elif ch == 'e' and i == 0:
                out.append('э')
            else:
                out.append(SINGLE.get(ch, ch))
            i += 1
    s = ''.join(out)
    if w[0].isupper():
        s = s[0].upper() + s[1:]
    return s


TOKEN = re.compile(r'[A-Za-z]+|_+|[^A-Za-z_]+')


def rus(name):
    if not name:
        return ''
    if name.lower().startswith('petlya'):
        name = name.split('+')[0]                # «Петля…+Отверстие…» -> только петля
    toks = TOKEN.findall(name)
    # скобки: «Полка__просвет_340_» -> «Полка (просвет 340)»
    paren_open = None
    if len(toks) >= 3 and toks[-1] == '_' and re.match(r'^[\d.,]+$', toks[-2] or ''):
        for k, t in enumerate(toks):
            if t == '__' and k > 0 and toks[k - 1][-1:].lower() not in CONS_LAT | {'l'}:
                paren_open = k
                break
            if t == '__' and k > 0 and toks[k - 1].lower() not in SOFT and toks[k - 1][-1:].lower() != 'l':
                paren_open = k
                break
    out = []
    for k, t in enumerate(toks):
        if t[0] == '_':
            prev = toks[k - 1] if k > 0 else ''
            nxt = toks[k + 1] if k + 1 < len(toks) else ''
            soft = False
            if prev and prev.isalpha() and not _is_latin_keep(prev) and prev[-1].lower() in CONS_LAT:
                lp = prev.lower()
                ln = nxt.lower() if nxt.isalpha() and nxt.islower() else ''
                if len(t) == 1 and ln and lp not in NOT_SOFT and (
                        ln in STRONG or (ln.startswith(STRONG) and len(ln) <= 5)
                        or (ln in ('ya', 'yo', 'yu', 'e', 'ef', 'em', 'en', 'evoy', 'evaya'))
                        or (lp.endswith('l') and len(ln) <= 3 and ln not in SHORT_WORDS)):
                    out.append('ь')     # склеиваем: «Frontal_naya» -> «Фронтальная»
                    continue
                if lp in NOT_SOFT:
                    soft = False
                elif lp in SOFT or (lp.endswith('l') and (len(t) >= 2 or not nxt)):
                    soft = True
            if soft:
                out.append('ь')
            if k == paren_open:
                out.append(' (')
            elif k == len(toks) - 1:
                if paren_open is not None:
                    out.append(')')
            else:
                out.append(' ')
        elif t[0].isalpha():
            nxt = toks[k + 1] if k + 1 < len(toks) else ''
            if len(t) == 1 and t.isupper() and nxt[:1] in tuple('0123456789.'):
                out.append(t)           # R2, T509HRW, HL.R.15
            else:
                out.append(word(t))
        else:
            out.append(t)
    s = ''.join(out)
    s = re.sub(r'\s+', ' ', s).strip().replace('ьэ', 'ье')
    s = s.replace(' ( ', ' (').replace('( ', '(').replace(' )', ')')
    s = re.sub(r'(\d)х(\d)', r'\1×\2', s)
    return s[:1].upper() + s[1:]


if __name__ == '__main__':
    import sys
    tests = ['Bokovina_levaya', 'Dver__pravaya_verkhnya', 'Fasad__petli_u_steny_D__598_×_727',
             'Polka__prosvet_340_', 'Frontal_naya', 'Antresol__nad_stopkoy', 'Antresol_',
             'Peregorodka_gorizontal_naya__razdel_dverets_1670_', 'Fasad_verkhniy_331_×_797',
             'Vyezd_shkafa', 'Poz._2_—_R2_otkatnaya__bel_yo_i_gladil_naya_stantsiya_331_×_2467_×_592',
             'Postirochnaya-mebel_', 'Stiral_naya_mashina_ASKO_W5096CW', 'Rel_ef_bokovin',
             'Perednyaya_panel_', 'Uplotnenie_Steel_Seal', 'Ryobra_barabana', 'Shchel__lyuchka',
             'Lyuchok_fil_tra', 'Kol_tso_lyuka', 'Pereklyuchatel__programm', 'Reshyotka_ventilyatsii',
             'Podpyatnik_kruglyy_D15_mm__pod_otverstie_5_mm__chernyy_HL.R.15.BL', 'Krysha', 'Dno',
             'Petlya_CLIP_top_BLUMOTION__Nakl.___dveri_ot_15_mm.__107_grad.__samorez__NI+Krestoobr._otv._samorez__NI',
             'Gorizontal_naya', 'Sushil_naya_mashina_ASKO_T509HRW', 'Konteyner_dlya_vody', 'Displey',
             'Knopka_start/pauza', 'Yashchik_vydvizhnoy', 'Ekstsentrik']
    for t in tests:
        sys.stdout.buffer.write(('%-45s -> %s\n' % (t[:45], rus(t))).encode('utf-8'))
