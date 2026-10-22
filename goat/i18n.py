"""Texts for the PDF and pictures in Russian and English.

Usage: i18n.set_lang("en"); i18n.T("key") or i18n.T("key", **fmt).
"""

LANG = "ru"

TEXT = {
    "ru": {
        "title": "Коза low-poly {version} — выкройка из бумаги",
        "short_title": "Коза low-poly {version}",
        "side_L": "Л",
        "side_R": "П",
        # характеристики
        "row_withers": "Высота в холке",
        "row_size": "Габарит (длина × ширина × высота с рогами)",
        "row_faces": "Граней (треугольников)",
        "row_pieces": "Деталей",
        "val_pieces": "{n} ({pairs} зеркальных пар Л/П)",
        "row_cuts": "Склеиваемых рёбер (номеров)",
        "row_sheets": "Листов с деталями (A4)",
        "row_material": "Материал",
        "row_tab": "Клапан под клей",
        "cm": "см",
        "mm": "мм",
        "map_caption": "Карта сборки: цвет = деталь, подпись = номер детали на листах. Л — левая сторона козы, П — правая.",
        "map_left": "левый бок — детали Л",
        "map_right": "правый бок — детали П",
        "map_front": "спереди-сверху",
        "map_bottom": "снизу",
        # легенда
        "legend_title": "Обозначения",
        "legend_cut": "Сплошная — линия реза.",
        "legend_mountain": "Штрих-пунктир — сгиб «гора»: сгибать от себя, ребро смотрит на вас (рисунок снаружи).",
        "legend_valley": "Пунктир — сгиб «долина»: сгибать на себя, получается желобок.",
        "legend_tab": "Серое — клапан под клей. Сгибается внутрь по основанию, мажется клеем, уходит под соседнюю деталь.",
        "legend_num": "Число у края — номер ребра. Края с одинаковыми номерами склеиваются друг с другом.",
        # порядок работы
        "steps_title": "Порядок работы",
        "steps": [
            "**1. Печать.",
            "Формат A4 (не Letter!), масштаб 100% («Фактический размер»). Проверьте линейкой отрезок 50 мм в шапке листа.",
            "**2. Материал.",
            "Проверенный вариант: обычная офисная бумага 80 г/м², наклеенная лицом наружу на тонкий картон сухим клеем "
            "(клеящий карандаш, двусторонняя плёнка, аэрозоль), затем под пресс. Для маленькой козы можно печатать "
            "сразу на плотной бумаге 160 г/м². Линии и номера остаются снаружи — так задумано.",
            "**3. Биговка — до вырезания.",
            "Продавите все линии сгиба (включая основания клапанов) по металлической линейке: деревянной палочкой, "
            "пустой шариковой ручкой или стилусом. Сгибы получатся ровными и острыми.",
            "**4. Вырезание.",
            "Макетным или строительным ножом с отламывающимся лезвием по металлической линейке. Клапаны не отрезайте.",
            "**5. Сгибание.",
            "«Горы» — от себя, «долины» — на себя, клапаны — внутрь. Почти плоские рёбра без линии не сгибают.",
            "**6. Клей.",
            "ПВА сохнет слишком долго — каждый шов приходится держать. Удобнее быстрый клей: суперклей-гель или "
            "контактный клей. Наносите зубочисткой; для пальцев держите рядом жидкость для снятия лака.",
            "**7. Порядок сборки (проверено).",
            "Голова целиком → передние ноги → задние ноги → бока от задних ног к передним. Получаются голова и две "
            "половины (Л и П) с ногами. Затем половины склеиваются сверху (спина, шея), приклеивается голова, "
            "последним закрывается живот — см. «Как закрыть фигуру».",
        ],
        # список деталей и финал
        "list_title": "Список деталей",
        "piece_line": "{a} / {b} — {region}, {faces} гр., листы {sa}/{sb}",
        "close_title": "Как закрыть фигуру",
        "close_text": [
            "Последний шов — по животу, между ногами: он внизу, и неидеальную склейку там почти не видно.",
            "На шве по животу все клапаны стоят на левых (Л) деталях: правая половина просто ложится сверху на торчащие "
            "клапаны, изнутри ничего держать не нужно. Рёбра этого шва: {nums}.",
            "Закрывайте от концов к середине. Последние 5–10 см — контактным способом: тонкий слой клея на клапаны и на "
            "край ответной детали, подождать 5–10 минут, сжать — схватывается сразу. Перед закрытием можно вложить груз "
            "в ноги, а в большую фигуру — 2–3 поперечные перегородки.",
        ],
        # шапка листа
        "sheet": "лист {i} из {n} · печать A4, 100%, без масштабирования",
        "check50": "50 мм — проверьте линейкой",
        "regions": {
            "body_f": "Тело, перёд", "body_r": "Тело, зад", "neck": "Шея", "head": "Голова",
            "ear": "Ухо", "horn": "Рог", "tail": "Хвост", "fleg": "Нога передняя", "hleg": "Нога задняя",
        },
    },
    "en": {
        "title": "Low-poly Goat {version} — papercraft pattern",
        "short_title": "Low-poly Goat {version}",
        "side_L": "L",
        "side_R": "R",
        "row_withers": "Height at withers",
        "row_size": "Size (length × width × height incl. horns)",
        "row_faces": "Faces (triangles)",
        "row_pieces": "Pieces",
        "val_pieces": "{n} ({pairs} mirrored L/R pairs)",
        "row_cuts": "Glued edges (numbers)",
        "row_sheets": "Sheets with pieces (A4)",
        "row_material": "Material",
        "row_tab": "Glue tab",
        "cm": "cm",
        "mm": "mm",
        "map_caption": "Assembly map: colour = piece, label = piece number on the sheets. L — goat's left side, R — right side.",
        "map_left": "left side — L pieces",
        "map_right": "right side — R pieces",
        "map_front": "front, from above",
        "map_bottom": "from below",
        "legend_title": "Legend",
        "legend_cut": "Solid line — cut.",
        "legend_mountain": "Dash-dot — mountain fold: fold away from you, the ridge points at you (print outside).",
        "legend_valley": "Dashed — valley fold: fold towards you, forms a groove.",
        "legend_tab": "Grey — glue tab. Fold it inwards along its base, apply glue, tuck it under the neighbouring piece.",
        "legend_num": "Number at an edge — edge ID. Edges with the same number are glued together.",
        "steps_title": "How to build",
        "steps": [
            "**1. Print.",
            "A4 paper (not Letter!), scale 100% (\"Actual size\"). Check the 50 mm bar in the sheet header with a ruler.",
            "**2. Material.",
            "Tested: plain 80 g/m² office paper glued face up onto thin cardboard with a dry glue (glue stick, "
            "double-sided film, spray), then pressed flat. For the small goat you can also print directly on 160 g/m² "
            "card. Lines and numbers stay on the outside — this is intended.",
            "**3. Score before cutting.",
            "Score every fold line (including tab bases) along a metal ruler with a wooden stick, an empty ballpoint pen "
            "or an embossing stylus. Folds will be straight and crisp.",
            "**4. Cut.",
            "Use a craft or snap-off utility knife along a metal ruler. Keep the tabs.",
            "**5. Fold.",
            "Mountains away from you, valleys towards you, tabs inwards. Nearly flat edges without a line are not folded.",
            "**6. Glue.",
            "White PVA glue dries too slowly — you have to hold every joint. Fast glue is much easier: superglue gel or "
            "contact cement. Apply with a toothpick; keep nail polish remover handy for your fingers.",
            "**7. Assembly order (tested).",
            "Whole head → front legs → hind legs → sides from the hind legs towards the front legs. You get the head and "
            "two halves (L and R) with legs. Then join the halves along the top (back, neck), attach the head and close "
            "the belly last — see \"Closing the figure\".",
        ],
        "list_title": "Parts list",
        "piece_line": "{a} / {b} — {region}, {faces} faces, sheets {sa}/{sb}",
        "close_title": "Closing the figure",
        "close_text": [
            "The last seam is the belly, between the legs: it is underneath, so an imperfect joint is barely visible.",
            "On the belly seam all tabs are on the left (L) pieces: the right half simply lies over the protruding tabs, "
            "nothing has to be held from inside. Edges of this seam: {nums}.",
            "Close from both ends towards the middle. Do the last 5–10 cm the contact way: a thin layer of glue on the "
            "tabs and on the mating edge, wait 5–10 minutes, press — it grabs instantly. Before closing you can put a "
            "weight into the legs, and 2–3 cross bulkheads into a large figure.",
        ],
        "sheet": "sheet {i} of {n} · print A4 at 100%, no scaling",
        "check50": "50 mm — check with a ruler",
        "regions": {
            "body_f": "Body, front", "body_r": "Body, rear", "neck": "Neck", "head": "Head",
            "ear": "Ear", "horn": "Horn", "tail": "Tail", "fleg": "Front leg", "hleg": "Hind leg",
        },
    },
}


def set_lang(lang):
    global LANG
    if lang not in TEXT:
        raise ValueError(f"unknown language {lang!r}; available: {', '.join(TEXT)}")
    LANG = lang


def T(key, **fmt):
    s = TEXT[LANG][key]
    return s.format(**fmt) if fmt and isinstance(s, str) else s


def piece_name(isl):
    return f"{isl.number}{T('side_' + isl.side)}"
