"""
GradioInterfaceYSTU — упрощённый интерфейс в стилистике ЯГТУ для маршрута /ystu.
Функциональность идентична основному приложению, но без панели настроек.
"""
import gradio as gr

from ui.gradio_app import GradioInterface
from ui.tabs.ystu_left_panel import build_ystu_left_panel
from ui.tabs.preview_tab import build_preview_tab
from ui.tabs.multiview_tab import build_multiview_tab
from ui.tabs.model_tab import build_model_tab
from ui.tabs.printable_tab import build_printable_tab
from ui.events_ystu import wire_events_ystu


YSTU_CSS = """
/* ── Цветовая схема интерфейса ЯГТУ ─────────────────────────────────── */
:root {
    --ystu-navy: #1F3F7C;
    --ystu-navy-dark: #17315F;
    --ystu-red: #D61924;
    --ystu-bg: #EEF2F8;
    --ystu-card: #FFFFFF;
    --ystu-border: #C9D2E1;
    --ystu-text: #152033;
    --ystu-muted: #58647A;
    --ystu-shell-max: min(96vw, 1780px);
}

html, body {
    background: radial-gradient(circle at 12% 0%, #F4F7FC 0%, var(--ystu-bg) 38%, #E8EDF7 100%) !important;
}

/* ── Шапка ───────────────────────────────────────────────────────────── */
.ystu-header {
    background: linear-gradient(90deg, var(--ystu-navy-dark) 0%, var(--ystu-navy) 75%);
    color: #FFFFFF;
    padding: 16px clamp(16px, 2vw, 30px);
    border-bottom: 3px solid var(--ystu-red);
    margin-bottom: 0 !important;
    border-radius: 8px 8px 0 0;
}

.ystu-header .ystu-logo-row {
    display: flex;
    align-items: center;
    gap: 14px;
}

.ystu-header .ystu-logo-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 68px;
    height: 42px;
    border-radius: 4px;
    background: var(--ystu-red);
    color: #FFFFFF;
    box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.18);
}

.ystu-header .ystu-logo-badge svg {
    width: 52px;
    height: 28px;
}

.ystu-header .ystu-wordmark {
    display: grid;
    gap: 2px;
}

.ystu-header .ystu-wordmark-main {
    font-size: 18px;
    font-weight: 700;
    letter-spacing: 0.6px;
}

.ystu-header .ystu-wordmark-sub {
    font-size: 10px;
    letter-spacing: 0.8px;
    text-transform: uppercase;
    opacity: 0.85;
}

.ystu-header h1 {
    margin: 0;
    font-size: clamp(17px, 1.35vw, 23px);
    font-weight: 700;
    line-height: 1.2;
    color: #FFFFFF !important;
}

.ystu-header p {
    margin: 4px 0 0;
    font-size: clamp(12px, 0.78vw, 14px);
    color: rgba(255, 255, 255, 0.84);
}

/* ── Подзаголовок ────────────────────────────────────────────────────── */
.ystu-subheader {
    background: #F2F5FA;
    border: 1px solid var(--ystu-border);
    border-top: 0;
    padding: 8px clamp(16px, 2vw, 30px);
    font-size: 12px;
    color: var(--ystu-muted);
    margin-bottom: 10px !important;
    border-radius: 0 0 8px 8px;
}

/* ── Общий контейнер ─────────────────────────────────────────────────── */
.gradio-container {
    font-family: "PT Sans", "Segoe UI", sans-serif !important;
    color: var(--ystu-text) !important;
    background: transparent !important;
    width: var(--ystu-shell-max) !important;
    max-width: var(--ystu-shell-max) !important;
    margin: 0 auto !important;
    padding: 8px clamp(12px, 1.25vw, 26px) 20px !important;
}

.ystu-main-grid {
    gap: clamp(10px, 1vw, 20px) !important;
    align-items: flex-start !important;
}

.ystu-left-pane {
    max-width: 520px;
}

.ystu-right-pane {
    min-width: 0;
}

/* ── Заголовки секций ────────────────────────────────────────────────── */
.gradio-container h3 {
    color: var(--ystu-navy) !important;
    font-size: 13px !important;
    font-weight: 700 !important;
    border-bottom: 2px solid var(--ystu-navy) !important;
    padding-bottom: 6px !important;
    margin-bottom: 10px !important;
    margin-top: 16px !important;
    text-transform: uppercase;
    letter-spacing: 0.45px;
}

/* ── Кнопки ──────────────────────────────────────────────────────────── */
.gradio-container button.primary {
    background: var(--ystu-navy) !important;
    border: 1px solid var(--ystu-navy) !important;
    color: #FFFFFF !important;
    font-weight: 700 !important;
    border-radius: 4px !important;
    transition: background 0.18s ease, border-color 0.18s ease;
}

.gradio-container button.primary:hover {
    background: var(--ystu-navy-dark) !important;
    border-color: var(--ystu-navy-dark) !important;
}

.gradio-container button.secondary {
    background: #FFFFFF !important;
    border: 1px solid var(--ystu-border) !important;
    color: var(--ystu-navy) !important;
    font-weight: 600 !important;
    border-radius: 4px !important;
    transition: border-color 0.18s ease, color 0.18s ease;
}

.gradio-container button.secondary:hover {
    border-color: var(--ystu-navy) !important;
    color: var(--ystu-navy-dark) !important;
}

/* ── Поля ввода ──────────────────────────────────────────────────────── */
.gradio-container input[type="text"],
.gradio-container textarea {
    border: 1px solid var(--ystu-border) !important;
    border-radius: 4px !important;
    background: #FFFFFF !important;
    font-family: "PT Sans", "Segoe UI", sans-serif !important;
}

.gradio-container input[type="text"]:focus,
.gradio-container textarea:focus {
    border-color: var(--ystu-navy) !important;
    outline: none !important;
    box-shadow: 0 0 0 2px rgba(31, 63, 124, 0.16) !important;
}

/* ── Вкладки ─────────────────────────────────────────────────────────── */
.gradio-container .tabs > .tab-nav {
    border-bottom: 1px solid var(--ystu-border) !important;
    margin-bottom: 8px !important;
}

.gradio-container .tabs > .tab-nav button {
    color: var(--ystu-muted) !important;
    font-weight: 600 !important;
    border-bottom: 2px solid transparent !important;
    border-radius: 0 !important;
    background: transparent !important;
    padding: 8px 10px !important;
    font-size: 13px !important;
}

.gradio-container .tabs > .tab-nav button.selected {
    color: var(--ystu-navy) !important;
    border-bottom: 2px solid var(--ystu-red) !important;
}

/* ── Аккордеоны ──────────────────────────────────────────────────────── */
.gradio-container .accordion > .label-wrap {
    background: #FFFFFF !important;
    border: 1px solid var(--ystu-border) !important;
    border-radius: 4px !important;
    color: var(--ystu-navy) !important;
    font-weight: 700 !important;
}

/* ── Карточки ────────────────────────────────────────────────────────── */
.gradio-container .block {
    background: var(--ystu-card) !important;
    border: 1px solid var(--ystu-border) !important;
    border-radius: 6px !important;
    box-shadow: 0 6px 14px rgba(17, 39, 83, 0.06) !important;
}

.ystu-right-pane .gallery {
    min-height: min(58vh, 620px);
}

/* ── Чекбоксы и радио ────────────────────────────────────────────────── */
.gradio-container input[type="checkbox"]:checked,
.gradio-container input[type="radio"]:checked {
    accent-color: var(--ystu-navy) !important;
}

/* ── Подвал ──────────────────────────────────────────────────────────── */
.ystu-footer {
    text-align: center;
    padding: 14px;
    font-size: 12px;
    color: var(--ystu-muted);
    border: 1px solid var(--ystu-border);
    border-radius: 8px;
    margin-top: 14px;
    background: #FFFFFF;
}

@media (max-width: 1280px) {
    .gradio-container {
        width: 99vw !important;
        max-width: 99vw !important;
    }

    .ystu-main-grid {
        gap: 12px !important;
    }

    .ystu-left-pane {
        max-width: none;
    }

    .ystu-right-pane .gallery {
        min-height: 420px;
    }
}

@media (max-width: 930px) {
    .ystu-header {
        border-radius: 6px 6px 0 0;
    }

    .ystu-header .ystu-logo-row {
        align-items: flex-start;
    }

    .ystu-header .ystu-logo-badge {
        width: 56px;
        height: 36px;
    }

    .ystu-header .ystu-wordmark {
        display: none;
    }

    .ystu-subheader {
        border-radius: 0 0 6px 6px;
    }
}
"""

YSTU_HEADER_HTML = """
<div class="ystu-header">
  <div class="ystu-logo-row">
        <span class="ystu-logo-badge" aria-hidden="true">
            <svg
                version="1.1"
                width="316.49438"
                height="97.175697"
                id="svg8"
                viewBox="0 0 316.49438 97.175697"
                sodipodi:docname="b543c2d0eb2cd839c85ec6c6d791f4c0.cdr"
                xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
                xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"
                xmlns="http://www.w3.org/2000/svg"
                xmlns:svg="http://www.w3.org/2000/svg">
                <defs
                    id="defs12" />
                <sodipodi:namedview
                    id="namedview10"
                    pagecolor="#ffffff"
                    bordercolor="#666666"
                    borderopacity="1.0"
                    inkscape:pageshadow="2"
                    inkscape:pageopacity="0.0"
                    inkscape:pagecheckerboard="0" />
                <path
                    d="m 121.6063,13.0649 h 2.3831 v 5.6024 h 2.9055 V 3.7837 h -5.7694 c -2.8638,0 -4.8917,1.7977 -4.8917,4.6406 0,1.8814 0.9825,3.3446 2.5503,4.0553 l -3.0727,6.1877 h 3.4491 z m 2.3831,-2.571 h -2.7176 c -1.296,0 -2.1532,-0.8989 -2.1532,-2.1115 0,-1.2331 0.8572,-2.0486 2.1532,-2.0486 h 2.7176 z m 17.0577,-2.0696 c 0,-2.5293 -1.8187,-4.6406 -4.9127,-4.6406 h -5.7693 v 14.8836 h 2.9055 v -5.6024 h 2.8638 c 3.094,0 4.9127,-2.1112 4.9127,-4.6406 z m -2.9058,0 c 0,1.2124 -0.8362,2.0276 -2.1532,2.0276 h -2.7175 V 6.3757 h 2.7175 c 1.317,0 2.1532,0.8362 2.1532,2.0486 z m 15.8454,2.8012 c 0,-2.8431 -0.0419,-4.5153 -1.5262,-5.9995 -1.0031,-1.0035 -2.2575,-1.5679 -3.9716,-1.5679 -1.7141,0 -2.9894,0.5644 -3.9926,1.5679 -1.4842,1.4842 -1.5052,3.1564 -1.5052,5.9995 0,2.8429 0.021,4.5153 1.5052,5.9995 1.0032,1.0032 2.2785,1.5676 3.9926,1.5676 1.7141,0 2.9685,-0.5644 3.9716,-1.5676 1.4843,-1.4842 1.5262,-3.1566 1.5262,-5.9995 z m -2.9058,0 c 0,2.8429 -0.1879,3.5328 -0.7316,4.1598 -0.4181,0.4808 -1.0661,0.8153 -1.8604,0.8153 -0.7942,0 -1.4425,-0.3345 -1.8813,-0.8153 -0.5437,-0.627 -0.7107,-1.3169 -0.7107,-4.1598 0,-2.8431 0.167,-3.5538 0.7107,-4.1808 0.4388,-0.4808 1.0871,-0.7946 1.8813,-0.7946 0.7943,0 1.4423,0.3138 1.8604,0.7946 0.5437,0.627 0.7316,1.3377 0.7316,4.1808 z m 16.3262,2.8638 h -2.9475 c -0.2925,1.2124 -1.0661,2.1113 -2.5084,2.1113 -0.7942,0 -1.4425,-0.2925 -1.8604,-0.7733 -0.5436,-0.6273 -0.7316,-1.3589 -0.7316,-4.2018 0,-2.8431 0.188,-3.5748 0.7316,-4.2018 0.4179,-0.4807 1.0662,-0.7736 1.8604,-0.7736 1.4423,0 2.1949,0.8992 2.4877,2.1116 h 2.9682 c -0.5434,-3.1147 -2.6757,-4.7036 -5.4559,-4.7036 -1.7141,0 -2.9684,0.5644 -3.9926,1.5679 -1.4842,1.4842 -1.5052,3.1564 -1.5052,5.9995 0,2.8429 0.021,4.5153 1.5052,5.9995 1.0242,1.0032 2.2785,1.5676 3.9926,1.5676 2.7593,0 4.9125,-1.5885 5.4559,-4.7033 z m 12.7306,4.578 V 3.7837 h -9.2605 v 6.7519 c 0,4.6615 -1.0661,5.5397 -2.55,5.5397 h -0.4181 v 2.592 h 1.1497 c 3.0937,0 4.6196,-1.7141 4.6196,-7.9645 V 6.3757 h 3.5538 v 12.2916 z m 14.9885,0 -5.4351,-14.8836 h -2.2785 l -5.4142,14.8836 h 3.0311 l 0.8989,-2.634 h 5.2886 l 0.8781,2.634 z m -4.6825,-5.0797 h -3.7001 l 1.8814,-5.4142 z m 15.2597,-2.5503 c 1.2334,-0.69 1.8397,-1.7351 1.8397,-3.1564 0,-2.5087 -1.7977,-4.0972 -4.5989,-4.0972 h -5.9786 v 14.8836 h 6.2294 c 2.8012,0 4.557,-1.6515 4.557,-4.2644 0,-1.0452 -0.2715,-1.8814 -0.9198,-2.5713 -0.3135,-0.3136 -0.5434,-0.4808 -1.1288,-0.7943 z M 199.8711,9.8039 V 6.3757 h 2.8432 c 1.1914,0 1.923,0.648 1.923,1.7141 0,1.0661 -0.7316,1.7141 -1.923,1.7141 z m 0,6.2714 v -3.6584 h 3.0311 c 1.1917,0 1.9443,0.69 1.9443,1.8187 0,1.1288 -0.7526,1.8397 -1.9443,1.8397 z m 21.1967,-1.986 h -2.9475 c -0.2925,1.2124 -1.0661,2.1113 -2.5084,2.1113 -0.7942,0 -1.4425,-0.2925 -1.8604,-0.7733 -0.5436,-0.6273 -0.7316,-1.3589 -0.7316,-4.2018 0,-2.8431 0.188,-3.5748 0.7316,-4.2018 0.4179,-0.4807 1.0662,-0.7736 1.8604,-0.7736 1.4423,0 2.1949,0.8992 2.4877,2.1116 h 2.9682 c -0.5434,-3.1147 -2.6757,-4.7036 -5.4559,-4.7036 -1.7141,0 -2.9684,0.5644 -3.9926,1.5679 -1.4842,1.4842 -1.5052,3.1564 -1.5052,5.9995 0,2.8429 0.021,4.5153 1.5052,5.9995 1.0242,1.0032 2.2785,1.5676 3.9926,1.5676 2.7593,0 4.9125,-1.5885 5.4559,-4.7033 z m 5.4561,4.578 V 3.7837 h -2.9058 v 14.8836 z m 8.8007,0 -5.4978,-7.9019 4.9961,-6.9817 h -3.4702 l -4.8078,7.0863 5.2259,7.7973 z m 12.9396,0 V 3.7837 h -2.592 l -5.7906,9.5321 V 3.7837 h -2.9055 v 14.8836 h 2.592 l 5.7906,-9.553 v 9.553 z M 260.7857,0 h -2.0486 c -0.0627,0.9196 -0.5851,1.296 -1.3377,1.296 -0.7526,0 -1.2753,-0.3764 -1.3379,-1.296 h -2.0486 c 0.0836,2.2575 1.7351,2.9892 3.3865,2.9892 1.6515,0 3.3027,-0.7317 3.3863,-2.9892 z m 2.2368,18.6673 V 3.7837 h -2.592 l -5.7906,9.5321 V 3.7837 h -2.9055 v 14.8836 h 2.592 l 5.7906,-9.553 v 9.553 z M 126.2052,31.8994 v -2.592 h -9.3651 V 44.191 h 2.9058 V 31.8994 Z m 0.1463,25.5237 v -2.592 h -10.6821 v 2.592 h 3.8883 v 12.2916 h 2.9055 V 57.4231 Z m 12.647,-20.6739 c 0,-2.8431 -0.0419,-4.5153 -1.5261,-5.9995 -1.0032,-1.0035 -2.2576,-1.5678 -3.9717,-1.5678 -1.7141,0 -2.9894,0.5643 -3.9926,1.5678 -1.4842,1.4842 -1.5052,3.1564 -1.5052,5.9995 0,2.8429 0.021,4.5153 1.5052,5.9996 1.0032,1.0031 2.2785,1.5675 3.9926,1.5675 1.7141,0 2.9685,-0.5644 3.9717,-1.5675 1.4842,-1.4843 1.5261,-3.1567 1.5261,-5.9996 z m -2.9058,0 c 0,2.8429 -0.1879,3.5328 -0.7316,4.1599 -0.4181,0.4807 -1.0661,0.8152 -1.8604,0.8152 -0.7942,0 -1.4425,-0.3345 -1.8813,-0.8152 -0.5437,-0.6271 -0.7107,-1.317 -0.7107,-4.1599 0,-2.8431 0.167,-3.5538 0.7107,-4.1808 0.4388,-0.4808 1.0871,-0.7945 1.8813,-0.7945 0.7943,0 1.4423,0.3137 1.8604,0.7945 0.5437,0.627 0.7316,1.3377 0.7316,4.1808 z m 16.3262,2.8639 h -2.9475 c -0.2925,1.2123 -1.0661,2.1112 -2.5084,2.1112 -0.7942,0 -1.4425,-0.2925 -1.8603,-0.7733 -0.5437,-0.6273 -0.7317,-1.3589 -0.7317,-4.2018 0,-2.8431 0.188,-3.5747 0.7317,-4.2018 0.4178,-0.4807 1.0661,-0.7735 1.8603,-0.7735 1.4423,0 2.1949,0.8991 2.4877,2.1115 h 2.9682 c -0.5434,-3.1147 -2.6756,-4.7035 -5.4559,-4.7035 -1.7141,0 -2.9684,0.5643 -3.9926,1.5678 -1.4842,1.4842 -1.5052,3.1564 -1.5052,5.9995 0,2.8429 0.021,4.5153 1.5052,5.9996 1.0242,1.0031 2.2785,1.5675 3.9926,1.5675 2.7593,0 4.9125,-1.5885 5.4559,-4.7032 z M 165.045,29.3074 h -3.0102 l -2.8221,7.17 -3.1147,-7.17 h -3.0311 l 4.7662,10.3266 -0.4391,1.0242 c -0.2716,0.6063 -0.7526,0.9408 -1.5469,0.9408 h -1.1707 v 2.592 h 1.777 c 1.7351,0 2.7593,-1.1707 3.3237,-2.5084 z m 12.9812,18.1865 V 41.599 h -1.7141 V 29.3074 h -8.9677 v 3.8044 c 0,3.4282 -0.5437,6.5849 -1.777,8.4872 h -1.4006 v 5.8949 h 2.8012 V 44.191 h 8.2573 v 3.3029 z m -4.6196,-5.8949 h -4.5989 c 1.0241,-2.0696 1.3169,-4.5989 1.3169,-7.5464 v -2.1532 h 3.282 z m 18.4374,2.592 -5.4352,-14.8836 h -2.2785 l -5.4141,14.8836 h 3.0311 l 0.8988,-2.6339 h 5.2886 l 0.8782,2.6339 z m -4.6826,-5.0797 h -3.7 l 1.8813,-5.4141 z m 17.2041,-5.1633 c 0,-2.5293 -1.8187,-4.6406 -4.9128,-4.6406 h -5.7693 V 44.191 h 2.9055 v -5.6024 h 2.8638 c 3.0941,0 4.9128,-2.1112 4.9128,-4.6406 z m -2.9058,0 c 0,1.2124 -0.8363,2.0276 -2.1532,2.0276 h -2.7176 v -4.0762 h 2.7176 c 1.3169,0 2.1532,0.8362 2.1532,2.0486 z m 15.8034,5.6651 h -2.9475 c -0.2925,1.2123 -1.0661,2.1112 -2.5083,2.1112 -0.7943,0 -1.4426,-0.2925 -1.8604,-0.7733 -0.5437,-0.6273 -0.7316,-1.3589 -0.7316,-4.2018 0,-2.8431 0.1879,-3.5747 0.7316,-4.2018 0.4178,-0.4807 1.0661,-0.7735 1.8604,-0.7735 1.4422,0 2.1948,0.8991 2.4876,2.1115 h 2.9682 c -0.5434,-3.1147 -2.6756,-4.7035 -5.4558,-4.7035 -1.7142,0 -2.9685,0.5643 -3.9926,1.5678 -1.4843,1.4842 -1.5052,3.1564 -1.5052,5.9995 0,2.8429 0.0209,4.5153 1.5052,5.9996 1.0241,1.0031 2.2784,1.5675 3.9926,1.5675 2.7592,0 4.9124,-1.5885 5.4558,-4.7032 z m 11.8735,-7.7137 v -2.592 h -10.6821 v 2.592 h 3.8883 V 44.191 h 2.9055 V 31.8994 Z m 11.0999,4.6616 c 1.2333,-0.6899 1.8397,-1.7351 1.8397,-3.1564 0,-2.5086 -1.7978,-4.0972 -4.599,-4.0972 h -5.9785 V 44.191 h 6.2294 c 2.8012,0 4.557,-1.6514 4.557,-4.2644 0,-1.0452 -0.2716,-1.8814 -0.9199,-2.5713 -0.3135,-0.3135 -0.5434,-0.4808 -1.1287,-0.7943 z m -5.8323,-1.2334 v -3.4282 h 2.8432 c 1.1914,0 1.923,0.648 1.923,1.7141 0,1.0661 -0.7316,1.7141 -1.923,1.7141 z m 0,6.2714 v -3.6584 h 3.0311 c 1.1917,0 1.9443,0.69 1.9443,1.8187 0,1.1288 -0.7526,1.8397 -1.9443,1.8397 z m 20.6532,2.592 v -2.592 h -6.8984 v -3.6164 h 5.8743 v -2.5923 h -5.8743 v -3.4909 h 6.8984 v -2.592 h -9.8039 V 44.191 Z m 13.6922,0 V 29.3074 h -2.9055 v 6.0829 h -5.038 v -6.0829 h -2.9055 V 44.191 h 2.9055 v -6.2294 h 5.038 v 6.2294 z m 14.3192,0 V 29.3074 h -2.9055 v 6.0829 h -5.038 v -6.0829 h -2.9055 V 44.191 h 2.9055 v -6.2294 h 5.038 v 6.2294 z m 18.6673,0 V 29.3074 h -2.9055 V 44.191 Z m -4.515,-4.6406 c 0,-2.7176 -1.9233,-4.6409 -4.8291,-4.6409 h -2.9475 V 29.3074 H 286.539 V 44.191 h 5.853 c 2.8848,0 4.8291,-1.9233 4.8291,-4.6406 z m -2.9058,0 c 0,1.2334 -0.8362,2.0486 -2.1532,2.0486 h -2.7176 v -4.0972 h 2.7176 c 1.317,0 2.1532,0.836 2.1532,2.0486 z m 19.9423,-14.0267 h -2.0486 c -0.0627,0.9196 -0.5851,1.296 -1.3377,1.296 -0.7526,0 -1.2753,-0.3764 -1.3379,-1.296 h -2.0486 c 0.0836,2.2576 1.7351,2.9892 3.3865,2.9892 1.6515,0 3.3027,-0.7316 3.3863,-2.9892 z m 2.2368,18.6673 V 29.3074 h -2.592 l -5.7906,9.5321 v -9.5321 h -2.9055 V 44.191 h 2.592 l 5.7906,-9.553 v 9.553 z M 138.5175,69.7147 v -2.592 h -6.8984 v -3.6164 h 5.8742 V 60.914 h -5.8742 v -3.4909 h 6.8984 v -2.592 h -9.8039 v 14.8836 z m 13.6088,0 -4.6408,-7.63 4.327,-7.2536 h -3.2819 l -2.613,4.8079 -2.592,-4.8079 h -3.3029 l 4.3271,7.2536 -4.6196,7.63 h 3.3236 l 2.8638,-5.1842 2.8848,5.1842 z m 12.6885,0 V 54.8311 h -2.9055 v 6.0829 h -5.038 v -6.0829 h -2.9056 v 14.8836 h 2.9056 v -6.2294 h 5.038 v 6.2294 z m 14.7583,0 V 54.8311 h -2.592 l -5.7906,9.5321 v -9.5321 h -2.9055 v 14.8836 h 2.592 l 5.7906,-9.553 v 9.553 z m 13.5459,0 V 54.8311 h -2.8848 v 6.7938 c -0.6061,0.1253 -1.923,0.3136 -2.8219,0.3136 -1.0454,0 -1.8607,-0.4808 -1.8607,-1.7768 v -5.3306 h -2.9055 v 6.0829 c 0,2.4667 1.9021,3.6165 3.8044,3.6165 1.5888,0 3.0104,-0.2716 3.7837,-0.3972 v 5.5814 z m 13.2741,0 v -2.592 h -6.8984 v -3.6164 h 5.8742 V 60.914 h -5.8742 v -3.4909 h 6.8984 v -2.592 h -9.8039 v 14.8836 z m 13.295,-4.5779 h -2.9474 c -0.2926,1.2124 -1.0661,2.1112 -2.5084,2.1112 -0.7943,0 -1.4426,-0.2925 -1.8604,-0.7733 -0.5437,-0.6273 -0.7316,-1.3589 -0.7316,-4.2018 0,-2.8431 0.1879,-3.5747 0.7316,-4.2018 0.4178,-0.4807 1.0661,-0.7735 1.8604,-0.7735 1.4423,0 2.1949,0.8991 2.4877,2.1115 h 2.9681 c -0.5434,-3.1147 -2.6756,-4.7035 -5.4558,-4.7035 -1.7141,0 -2.9684,0.5643 -3.9926,1.5678 -1.4842,1.4842 -1.5052,3.1564 -1.5052,5.9995 0,2.8429 0.021,4.5153 1.5052,5.9996 1.0242,1.0031 2.2785,1.5675 3.9926,1.5675 2.7592,0 4.9124,-1.5885 5.4558,-4.7032 z m 5.4562,4.5779 V 54.8311 h -2.9058 v 14.8836 z m 8.8007,0 -5.4978,-7.9018 4.9961,-6.9818 h -3.4702 l -4.8079,7.0864 5.226,7.7972 z m 12.9396,0 V 54.8311 h -2.592 l -5.7906,9.5321 v -9.5321 h -2.9055 v 14.8836 h 2.592 l 5.7906,-9.553 v 9.553 z m 12.5215,-18.6672 h -2.0486 c -0.0627,0.9195 -0.5851,1.296 -1.3377,1.296 -0.7526,0 -1.2753,-0.3765 -1.338,-1.296 h -2.0486 c 0.0837,2.2575 1.7351,2.9891 3.3866,2.9891 1.6515,0 3.3026,-0.7316 3.3863,-2.9891 z m 2.2368,18.6672 V 54.8311 h -2.592 l -5.7906,9.5321 v -9.5321 h -2.9055 v 14.8836 h 2.592 l 5.7906,-9.553 v 9.553 z M 127.1041,80.3549 h -3.0101 l -2.8222,7.1699 -3.1147,-7.1699 h -3.0311 l 4.7662,10.3266 -0.4391,1.0241 c -0.2716,0.6064 -0.7526,0.9409 -1.5469,0.9409 h -1.1707 v 2.592 h 1.777 c 1.7351,0 2.7593,-1.1708 3.3237,-2.5084 z m 12.6677,14.8836 V 80.3549 h -2.9055 v 6.0828 h -5.038 v -6.0828 h -2.9055 v 14.8836 h 2.9055 V 89.009 h 5.038 v 6.2295 z m 14.7583,0 V 80.3549 h -2.592 l -5.7906,9.532 v -9.532 h -2.9055 v 14.8836 h 2.592 l 5.7906,-9.5531 v 9.5531 z m 12.208,-7.6301 c 1.2333,-0.6899 1.8397,-1.7351 1.8397,-3.1563 0,-2.5087 -1.7978,-4.0972 -4.599,-4.0972 h -5.9785 v 14.8836 h 6.2294 c 2.8012,0 4.557,-1.6515 4.557,-4.2645 0,-1.0451 -0.2716,-1.8813 -0.9199,-2.5713 -0.3135,-0.3135 -0.5434,-0.4808 -1.1287,-0.7943 z m -5.8323,-1.2333 v -3.4282 h 2.8432 c 1.1914,0 1.923,0.648 1.923,1.7141 0,1.0661 -0.7316,1.7141 -1.923,1.7141 z m 0,6.2714 v -3.6584 h 3.0311 c 1.1917,0 1.9443,0.6899 1.9443,1.8187 0,1.1287 -0.7526,1.8397 -1.9443,1.8397 z m 20.6532,2.592 v -2.592 h -6.8984 V 89.03 h 5.8743 v -2.5923 h -5.8743 v -3.4908 h 6.8984 v -2.592 h -9.8039 v 14.8836 z m 13.5253,-10.243 c 0,-2.5294 -1.8187,-4.6406 -4.9128,-4.6406 h -5.7693 v 14.8836 h 2.9055 v -5.6024 h 2.8638 c 3.0941,0 4.9128,-2.1113 4.9128,-4.6406 z m -2.9058,0 c 0,1.2123 -0.8363,2.0276 -2.1532,2.0276 h -2.7176 v -4.0762 h 2.7176 c 1.3169,0 2.1532,0.8362 2.1532,2.0486 z m 15.8034,5.665 h -2.9475 c -0.2925,1.2124 -1.0661,2.1112 -2.5083,2.1112 -0.7943,0 -1.4426,-0.2925 -1.8604,-0.7732 -0.5437,-0.6274 -0.7316,-1.359 -0.7316,-4.2018 0,-2.8432 0.1879,-3.5748 0.7316,-4.2018 0.4178,-0.4808 1.0661,-0.7736 1.8604,-0.7736 1.4422,0 2.1948,0.8991 2.4876,2.1115 h 2.9682 c -0.5434,-3.1147 -2.6756,-4.7035 -5.4558,-4.7035 -1.7141,0 -2.9685,0.5644 -3.9926,1.5678 -1.4843,1.4842 -1.5052,3.1564 -1.5052,5.9996 0,2.8428 0.0209,4.5153 1.5052,5.9995 1.0241,1.0032 2.2785,1.5675 3.9926,1.5675 2.7592,0 4.9124,-1.5885 5.4558,-4.7032 z m 13.7968,4.578 V 80.3549 h -2.592 l -5.7906,9.532 v -9.532 h -2.9055 v 14.8836 h 2.592 l 5.7906,-9.5531 v 9.5531 z m 13.0442,-12.2916 v -2.592 h -10.6821 v 2.592 h 3.8883 v 12.2916 h 2.9055 V 82.9469 Z m 12.166,12.2916 v -2.592 h -6.8984 V 89.03 h 5.8742 v -2.5923 h -5.8742 v -3.4908 h 6.8984 v -2.592 h -9.8039 v 14.8836 z m 12.4172,-12.2916 v -2.592 H 248.724 v 2.592 h 3.8883 v 12.2916 h 2.9055 V 82.9469 Z"
                    style="fill:#6e6f70;fill-rule:evenodd"
                    id="path2" />
                <path
                    d="M 95.652,75.9197 C 92.1718,88.1706 80.9061,97.1757 67.5411,97.1757 H 37.198 v -21.256 z"
                    style="fill:#f07c00;fill-rule:evenodd"
                    id="path4" />
                <path
                    d="M 0,67.9487 C 0,60.888 2.4729,54.402 6.6426,49.3497 v 0 C 2.4585,44.2931 0,37.8249 0,30.7507 0,14.6118 13.0881,1.5236 29.227,1.5236 H 95.652 V 22.7797 H 29.227 c -4.4015,0 -7.971,3.5694 -7.971,7.971 0,4.4015 3.5695,7.971 7.971,7.971 h 66.425 v 21.256 H 29.227 c -4.4015,0 -7.971,3.5694 -7.971,7.971 v 29.227 H 0 Z"
                    style="fill:#004589;fill-rule:evenodd"
                    id="path6" />
            </svg>
        </span>
        <div class="ystu-wordmark">
            <span class="ystu-wordmark-main">ЯГТУ</span>
            <span class="ystu-wordmark-sub">Yaroslavl State Technical University</span>
        </div>
    <div>
      <h1>Ярославский государственный технический университет</h1>
      <p>Система автоматизированной генерации 3D-моделей для печати</p>
    </div>
  </div>
</div>
<div class="ystu-subheader">
  Кафедра информационных технологий &nbsp;&bull;&nbsp; Лаборатория аддитивных технологий
</div>
"""

YSTU_FOOTER_HTML = """
<div class="ystu-footer">
  &copy; 2024 ЯГТУ &mdash; Ярославский государственный технический университет.
  Все права защищены.
</div>
"""


class GradioInterfaceYSTU(GradioInterface):
    """Упрощённый интерфейс ЯГТУ: та же функциональность, без панели настроек."""

    def build_interface(self):
        """Собирает упрощённый Gradio Blocks в стилистике ЯГТУ."""
        with gr.Blocks(
            title="ЯГТУ — Генерация 3D-моделей",
            css=YSTU_CSS,
            theme=gr.themes.Base(
                primary_hue=gr.themes.colors.blue,
                neutral_hue=gr.themes.colors.slate,
                font=gr.themes.GoogleFont("PT Sans"),
            ),
        ) as demo:
            session_id = gr.Textbox(value="default", visible=False, elem_id="session_id")

            gr.HTML(YSTU_HEADER_HTML)

            with gr.Row(elem_classes=["ystu-main-grid"]):
                left = build_ystu_left_panel(self.local_models, self.config)

                with gr.Column(scale=2, min_width=860, elem_classes=["ystu-right-pane"]):
                    with gr.Tabs():
                        preview   = build_preview_tab()
                        mview     = build_multiview_tab()
                        model     = build_model_tab()
                        printable = build_printable_tab()

            gr.HTML(YSTU_FOOTER_HTML)

            components = {
                **left, **preview, **mview, **model, **printable,
                "session_id": session_id,
            }
            wire_events_ystu(self, components)

        return demo
