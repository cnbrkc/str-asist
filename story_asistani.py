import os
import re
import base64
import tempfile
import streamlit as st
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps


def get_project_root() -> str:
    return os.getcwd()


def log(msg: str, level: str = "INFO") -> None:
    print(f"[{level}] {msg}")


# ── TASARIM SABİTLERİ ──
CANVAS_WIDTH  = 1080
CANVAS_HEIGHT = 1920

BG_COLOR_RGBA = (18, 25, 36, 255)
TEXT_COLOR    = (255, 255, 255, 255)

TITLE_STROKE_COLOR = (0, 0, 0, 230)
BODY_STROKE_COLOR  = (0, 0, 0, 210)
TITLE_STROKE_WIDTH = 2
BODY_STROKE_WIDTH  = 2

OVERLAY_ALPHA = 90

FONT_BOLD_PATH = os.path.join(get_project_root(), "assets", "Roboto-Bold.ttf")
FONT_REG_PATH  = os.path.join(get_project_root(), "assets", "Roboto-Regular.ttf")


def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = FONT_BOLD_PATH if bold else FONT_REG_PATH
    if not os.path.exists(path):
        log(f"Font bulunamadi: {path}. Varsayilan kullaniliyor.", "WARNING")
        return ImageFont.load_default()
    return ImageFont.truetype(path, size)


def _wrap_text(draw, text, font, max_width, stroke_width=0):
    words = text.split()
    lines, current = [], ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font, stroke_width=stroke_width, anchor="lt")
        if (bbox[2] - bbox[0]) <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
                current = ""
            bw = draw.textbbox((0, 0), word, font=font, stroke_width=stroke_width, anchor="lt")
            if (bw[2] - bw[0]) > max_width:
                tmp = ""
                for ch in word:
                    t2 = tmp + ch
                    bc = draw.textbbox((0, 0), t2, font=font, stroke_width=stroke_width, anchor="lt")
                    if (bc[2] - bc[0]) <= max_width:
                        tmp = t2
                    else:
                        if tmp:
                            lines.append(tmp)
                        tmp = ch
                current = tmp
            else:
                current = word
    if current:
        lines.append(current)
    return lines


def _fit_cover(img, tw, th):
    return ImageOps.fit(img, (tw, th), method=Image.LANCZOS, centering=(0.5, 0.5))


def _fit_contain(img, mw, mh):
    r = min(mw / img.width, mh / img.height)
    return img.resize((max(1, int(img.width * r)), max(1, int(img.height * r))), Image.LANCZOS)


def _prepare_text(post_text):
    lines = [ln.strip() for ln in (post_text or "").split("\n") if ln.strip()]
    title = lines[0] if lines else ""
    if title:
        title = re.sub(r"\s+", " ", title).strip().upper()
    body = "\n".join(lines[1:]) if len(lines) > 1 else ""
    return title, body


def _draw_centered_line(canvas, x_center, y_top, text, font, fill, stroke_width, stroke_fill):
    draw = ImageDraw.Draw(canvas)
    b = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width, anchor="lt")
    lh = b[3] - b[1]
    draw.text((x_center, y_top), text, font=font, fill=fill,
              stroke_width=stroke_width, stroke_fill=stroke_fill, anchor="mt")
    return lh


# ═══════════════════════════════════════════════════════════
#  ANA FONKSİYON — "İçerik Kral" + 1-1-1-1-3 yerleşim
#
#  Gap bütçesi = 7 birim. Dağılım:
#     1 × gap  → üst margin
#     1 × gap  → logo  ↔ başlık
#     1 × gap  → başlık ↔ foto
#     1 × gap  → foto  ↔ alt metin
#     3 × gap  → alt margin  (uzun alt metne bol nefes)
#
#  Formül:  g = (1920 − içerik) / 7
#  • Fontlar makul başlar (64 / 46)
#  • GAP_MIN = 30  → margin sigortası
#  • GAP_MAX = 95  → içerik azken dev boşluk yok
# ═══════════════════════════════════════════════════════════
def create_social_card(post_text: str, image_path: str, output_path: str) -> str:
    try:
        title, body = _prepare_text(post_text)

        # ── Sabitler ──
        SIDE_PAD   = 60
        MAX_TEXT_W = CANVAS_WIDTH - 2 * SIDE_PAD
        LOGO_SIZE  = 210
        IMG_MAX_W  = CANVAS_WIDTH - 120

        TITLE_FONT_MAX = 64
        TITLE_FONT_MIN = 44
        BODY_FONT_MAX  = 42
        BODY_FONT_MIN  = 30
        TITLE_LINE_GAP = 6
        BODY_LINE_GAP  = 5

        IMG_H_MAX = 820
        IMG_H_MIN = 260

        GAP_MIN = 30
        GAP_MAX = 95

        # ── Gap dağılım katsayıları (1-1-1-1-3) ──
        TOP_MARGIN_GAP    = 1    # üst margin = 1 × gap
        BOTTOM_MARGIN_GAP = 3    # alt  margin = 3 × gap  (otomatik birikir)

        logo_path = os.path.join(get_project_root(), "assets", "logo.png")
        has_logo  = os.path.exists(logo_path)
        has_image = bool(image_path) and os.path.exists(image_path)

        src_img = None
        if has_image:
            try:
                src_img = Image.open(image_path).convert("RGB")
            except Exception as e:
                log(f"Gorsel acilamadi: {e}", "WARNING")
                has_image = False

        # ── Eleman listesi ──
        elem_keys = []
        if has_logo:  elem_keys.append("logo")
        if title:     elem_keys.append("title")
        if has_image: elem_keys.append("image")
        if body:      elem_keys.append("body")

        num_elems = len(elem_keys)
        # Toplam gap = üst(1) + ara(n-1) + alt(3) = (n-1) + 4 = n + 3
        num_gaps = num_elems + 3

        dummy = Image.new("RGB", (1, 1))
        dd    = ImageDraw.Draw(dummy)

        def measure_title(fs):
            if not title:
                return 0, [], None
            f = _get_font(fs, bold=True)
            lns = _wrap_text(dd, title, f, MAX_TEXT_W, TITLE_STROKE_WIDTH)
            h = sum(
                (dd.textbbox((0, 0), l, font=f, stroke_width=TITLE_STROKE_WIDTH, anchor="lt")[3]
                 - dd.textbbox((0, 0), l, font=f, stroke_width=TITLE_STROKE_WIDTH, anchor="lt")[1])
                + TITLE_LINE_GAP for l in lns)
            if lns:
                h -= TITLE_LINE_GAP
            return h, lns, f

        def measure_body(fs):
            if not body:
                return 0, [], None
            f = _get_font(fs, bold=False)
            lns = _wrap_text(dd, body, f, MAX_TEXT_W, BODY_STROKE_WIDTH)
            h = sum(
                (dd.textbbox((0, 0), l, font=f, stroke_width=BODY_STROKE_WIDTH, anchor="lt")[3]
                 - dd.textbbox((0, 0), l, font=f, stroke_width=BODY_STROKE_WIDTH, anchor="lt")[1])
                + BODY_LINE_GAP for l in lns)
            if lns:
                h -= BODY_LINE_GAP
            return h, lns, f

        def fit_image(slot_h):
            if src_img is None:
                return 0, None
            fitted = _fit_contain(src_img, IMG_MAX_W, slot_h)
            return fitted.height, fitted

        # ══════════════════════════════════════════════════
        #  HESAP: içerik max başlar, gap arta kalan.
        # ══════════════════════════════════════════════════
        tfs        = TITLE_FONT_MAX
        bfs        = BODY_FONT_MAX
        img_slot_h = IMG_H_MAX

        while True:
            title_h, title_lines, font_t = measure_title(tfs)
            body_h,  body_lines,  font_b = measure_body(bfs)
            actual_img_h, fitted_img     = fit_image(img_slot_h)

            content_h = 0
            if has_logo:  content_h += LOGO_SIZE
            if title:     content_h += title_h
            if has_image: content_h += actual_img_h
            if body:      content_h += body_h

            gap = (CANVAS_HEIGHT - content_h) / num_gaps

            if gap >= GAP_MIN:
                break

            shrunk = False
            if tfs > TITLE_FONT_MIN:
                tfs = max(TITLE_FONT_MIN, tfs - 2); shrunk = True
            if bfs > BODY_FONT_MIN:
                bfs = max(BODY_FONT_MIN, bfs - 2); shrunk = True
            if img_slot_h > IMG_H_MIN:
                img_slot_h = max(IMG_H_MIN, img_slot_h - 12); shrunk = True
            if not shrunk:
                gap = GAP_MIN
                break

        if gap > GAP_MAX:
            gap = GAP_MAX

        # ── Blok yüksekliği ve başlangıç Y ──
        # Blok = üst(1g) + elemanlar + ara gapler + alt(3g) = content + 7g
        total_block_h = content_h + num_gaps * gap
        y_start = (CANVAS_HEIGHT - total_block_h) // 2

        # ══════════════════════════════════════════════════
        #  ÇİZİM
        # ══════════════════════════════════════════════════
        canvas = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), BG_COLOR_RGBA)

        if src_img is not None:
            try:
                bg = _fit_cover(src_img, CANVAS_WIDTH, CANVAS_HEIGHT)
                bg = bg.filter(ImageFilter.GaussianBlur(30))
                canvas.paste(bg, (0, 0))
            except Exception as e:
                log(f"Blur arka plan: {e}", "WARNING")

        overlay = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), (18, 25, 36, OVERLAY_ALPHA))
        canvas = Image.alpha_composite(canvas, overlay)

        # ★ ÜST MARJİN = 1 × gap  (eskiden 2 idi)
        y = y_start + TOP_MARGIN_GAP * gap

        for i, key in enumerate(elem_keys):

            if key == "logo":
                try:
                    logo = Image.open(logo_path).convert("RGBA")
                    logo = logo.resize((LOGO_SIZE, LOGO_SIZE), Image.LANCZOS)
                    lx = (CANVAS_WIDTH - LOGO_SIZE) // 2
                    canvas.paste(logo, (lx, int(y)), logo)
                except Exception as e:
                    log(f"Logo: {e}", "WARNING")
                y += LOGO_SIZE

            elif key == "title":
                for ln in title_lines:
                    lh = _draw_centered_line(
                        canvas, CANVAS_WIDTH // 2, int(y), ln,
                        font_t, TEXT_COLOR, TITLE_STROKE_WIDTH, TITLE_STROKE_COLOR)
                    y += lh + TITLE_LINE_GAP
                y -= TITLE_LINE_GAP

            elif key == "image":
                iw, ih = fitted_img.size
                ix = (CANVAS_WIDTH - iw) // 2

                mask = Image.new("L", (iw, ih), 0)
                ImageDraw.Draw(mask).rounded_rectangle((0, 0, iw, ih), radius=22, fill=255)

                sp = 30
                shadow = Image.new("RGBA", (iw + sp * 2, ih + sp * 2), (0, 0, 0, 0))
                sd = ImageDraw.Draw(shadow)
                for k in range(8):
                    sd.rounded_rectangle(
                        (8 + k * 2, 8 + k * 2, iw + 8 + k * 2, ih + 8 + k * 2),
                        radius=26, fill=(0, 0, 0, max(0, 60 - k * 6)))
                shadow = shadow.filter(ImageFilter.GaussianBlur(8))
                canvas.alpha_composite(shadow, dest=(ix - sp, int(y) - 6))

                canvas.paste(fitted_img.convert("RGBA"), (ix, int(y)), mask)

                ImageDraw.Draw(canvas).rounded_rectangle(
                    (ix, int(y), ix + iw, int(y) + ih),
                    radius=22, outline=(255, 255, 255, 70), width=2)

                y += ih

            elif key == "body":
                for ln in body_lines:
                    lh = _draw_centered_line(
                        canvas, CANVAS_WIDTH // 2, int(y), ln,
                        font_b, TEXT_COLOR, BODY_STROKE_WIDTH, BODY_STROKE_COLOR)
                    y += lh + BODY_LINE_GAP
                y -= BODY_LINE_GAP

            # Elemanlar arası 1 × gap (son elemandan sonra eklenmez → altta 3g kalır)
            if i < len(elem_keys) - 1:
                y += gap

        # ── Kaydet ──
        final = canvas.convert("RGB")
        if (output_path or "").lower().endswith(".png"):
            final.save(output_path, format="PNG", optimize=True, compress_level=4)
        else:
            final.save(output_path, format="JPEG", quality=95, optimize=True, subsampling=0)

        log(f"Kart olusturuldu: {output_path}  |  gap={gap:.0f}  title={tfs}  body={bfs}  img_h={actual_img_h}  dagilim=1-1-1-1-3")
        return output_path

    except Exception as e:
        log(f"Kart hatasi: {e}", "ERROR")
        return image_path


# ═══════════════════════════════════════════════════════════
#  STREAMLIT ARAYÜZÜ
# ═══════════════════════════════════════════════════════════
st.set_page_config(page_title="Story Asistanım", page_icon="📸", layout="centered")
st.title("📸 Story Asistanım")
st.markdown("Fotoğrafı yükle, metinleri yaz, saniyeler içinde o muhteşem şablonu indir!")

col1, col2 = st.columns(2)
with col1:
    title_text = st.text_input(
        "📝 Başlık (Marka / Model / Konu)",
        value="",
        placeholder="Örn: DAYANIKLILIĞIN ADI: TOYOTA COROLLA!")
with col2:
    body_text = st.text_area(
        "📄 Alt Metin (Fiyat / Detay)",
        value="",
        placeholder="Örn: Sadece bu hafta geçerlidir! Fiyat: 1.250.000 TL",
        height=150)

uploaded_file = st.file_uploader("⬆️ Araç/Haber Görselini Yükle",
                                 type=['jpg', 'jpeg', 'png'])

if st.button("🎨 Şablonu Oluştur", type="primary", use_container_width=True):
    if uploaded_file is None:
        st.warning("Lütfen bir görsel yükleyin!")
    else:
        with st.spinner("Şablon hazırlanıyor..."):
            temp_dir    = tempfile.mkdtemp()
            input_path  = os.path.join(temp_dir, "input_img.png")
            output_path = os.path.join(temp_dir, "story_card.png")

            with open(input_path, "wb") as f:
                f.write(uploaded_file.getbuffer())

            full_text   = f"{title_text}\n{body_text}"
            result_path = create_social_card(full_text, input_path, output_path)

            if result_path and result_path != input_path and os.path.exists(result_path):
                st.success("Şablon başarıyla oluşturuldu!")
                with open(result_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()

                st.markdown("""
                <div style="background-color:#1E293B; padding:15px; border-radius:10px;
                            border:1px solid #334155; margin-bottom:20px;">
                    <p style="color:#FBBF24; font-weight:bold; margin:0 0 5px 0;">
                        📱 iPhone Kullanıcıları İçin Önemli Not:</p>
                    <p style="color:#E2E8F0; font-size:14px; margin:0;">
                    Görselin üzerine parmağınızla <b>basılı tutun</b> →
                    <b>"Fotoğrafa Kaydet"</b>.</p>
                </div>""", unsafe_allow_html=True)

                st.markdown(
                    f'<img src="data:image/png;base64,{b64}" '
                    f'style="width:100%; border-radius:15px; '
                    f'box-shadow: 0 4px 15px rgba(0,0,0,0.5);" alt="Story Kart">',
                    unsafe_allow_html=True)
            else:
                st.error("Şablon oluşturulamadı. Konsoldaki log'a bak.")
