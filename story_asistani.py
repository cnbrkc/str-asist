import os
import re
import base64
import tempfile
import streamlit as st
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ── Ayarlar ───────────────────────────────────────────────────────────────────
CANVAS_WIDTH = 2160
CANVAS_HEIGHT = 3840
BG_COLOR_RGBA = (18, 25, 36, 255)
TEXT_COLOR = (255, 255, 255)

FONT_BOLD_PATH = os.path.join("assets", "Roboto-Bold.ttf")
FONT_REG_PATH = os.path.join("assets", "Roboto-Regular.ttf")

# ── LAYOUT SABİTLERİ ──────────────────────────────────────────────────────────
MARGIN_X = 160                 # Sol/sağ kenar boşluğu
GAP = 70                       # TÜM elemanlar arası EŞİT boşluk
LOGO_SIZE = 220                # Logo kare boyutu
PHOTO_BOX_W = CANVAS_WIDTH - (MARGIN_X * 2)   # 1840
PHOTO_BOX_H = 1400             # Fotoğrafın sabit kutu yüksekliği
SAFE_MARGIN = 90               # Taşma olursa kenarda kalacak minimum pay

# Metin kutusu maksimum yükseklikleri (auto-shrink buralara sığdırır)
TITLE_MAX_H = 380
BODY_MAX_H = 760


# ── Türkçe Büyük Harf Dönüşümü ───────────────────────────────────────────────
def turkish_upper(text: str) -> str:
    return (text
            .replace('i', 'İ')
            .replace('ı', 'I')
            .upper())


def _get_font(size: int, bold: bool = False):
    path = FONT_BOLD_PATH if bold else FONT_REG_PATH
    if not os.path.exists(path):
        st.error(f"Font bulunamadı: {path}. Lütfen assets klasörüne fontları koy.")
        return ImageFont.load_default()
    return ImageFont.truetype(path, size)


def _wrap_text(draw, text, font, max_width):
    words = text.split()
    lines, current_line = [], ""
    for word in words:
        test_line = f"{current_line} {word}".strip()
        bbox = draw.textbbox((0, 0), test_line, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)
    return lines


def _measure_lines(draw, lines, font, line_spacing):
    h = 0
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        h += (bbox[3] - bbox[1])
    h += max(0, len(lines) - 1) * line_spacing
    return h


def _fit_text_in_box(draw, text, size_start, size_min,
                     max_width, max_height, bold=False, line_spacing=28):
    """Metni kutuya sığdırır; sığmazsa fontu 4'er küçültür."""
    size = size_start
    while size >= size_min:
        font = _get_font(size, bold=bold)
        lines = _wrap_text(draw, text, font, max_width)
        h = _measure_lines(draw, lines, font, line_spacing)
        if h <= max_height:
            return lines, font, h
        size -= 4
    font = _get_font(size_min, bold=bold)
    lines = _wrap_text(draw, text, font, max_width)
    h = _measure_lines(draw, lines, font, line_spacing)
    return lines, font, h


def create_social_card(post_text: str, image_path: str, output_path: str) -> str:
    try:
        lines = [ln.strip() for ln in post_text.split("\n") if ln.strip()]
        title = lines[0] if lines else "OTOXTRA HABER"
        title = re.sub(r'[^a-zA-Z0-9ÇĞİÖŞÜçğıöşü\s]', '', title).strip()
        title = turkish_upper(title)
        body = "\n".join(lines[1:]) if len(lines) > 1 else ""

        # Ölçüm için geçici draw
        dummy_draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        content_width = CANVAS_WIDTH - (MARGIN_X * 2)

        # Metinleri hazırla (auto-shrink)
        title_lines, title_font, title_h = _fit_text_in_box(
            dummy_draw, title, 110, 56, content_width, TITLE_MAX_H,
            bold=True, line_spacing=30)

        if body.strip():
            body_lines, body_font, body_h = _fit_text_in_box(
                dummy_draw, body, 70, 38, content_width, BODY_MAX_H,
                bold=False, line_spacing=24)
        else:
            body_lines, body_font, body_h = [], None, 0

        # ── Blok yüksekliğini hesapla (logo + 3*GAP + title + photo + body) ──
        has_body = body_h > 0
        gap_count = 2 + (1 if has_body else 0)   # logo-title, title-photo, [photo-body]
        block_h = LOGO_SIZE + title_h + PHOTO_BOX_H + (body_h if has_body else 0) \
                  + gap_count * GAP

        # Taşma koruması: sığmıyorsa fotoğraftan kıs (fotoğraf esnek eleman)
        available = CANVAS_HEIGHT - 2 * SAFE_MARGIN
        if block_h > available:
            overflow = block_h - available
            new_photo_h = max(600, PHOTO_BOX_H - overflow)
            block_h -= (PHOTO_BOX_H - new_photo_h)
            photo_box_h = new_photo_h
        else:
            photo_box_h = PHOTO_BOX_H

        # ── BLOĞU DİKEY ORTALA ────────────────────────────────────────────────
        y_start = (CANVAS_HEIGHT - block_h) // 2
        y = y_start

        # ── Canvas + bulanık arka plan ───────────────────────────────────────
        canvas = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), BG_COLOR_RGBA)

        if image_path and os.path.exists(image_path):
            img_raw = Image.open(image_path).convert("RGB")
            ir = img_raw.width / img_raw.height
            cr = CANVAS_WIDTH / CANVAS_HEIGHT
            if ir > cr:
                b_h, b_w = CANVAS_HEIGHT, int(CANVAS_HEIGHT * ir)
            else:
                b_w, b_h = CANVAS_WIDTH, int(CANVAS_WIDTH / ir)
            blur_img = img_raw.resize((b_w, b_h), Image.LANCZOS) \
                              .filter(ImageFilter.GaussianBlur(140))
            l = (b_w - CANVAS_WIDTH) // 2
            t = (b_h - CANVAS_HEIGHT) // 2
            blur_img = blur_img.crop((l, t, l + CANVAS_WIDTH, t + CANVAS_HEIGHT))
            canvas.paste(blur_img, (0, 0))

        # Üst/alt karartma
        overlay = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 0))
        ov_draw = ImageDraw.Draw(overlay)
        fade = 1200
        for yy in range(CANVAS_HEIGHT):
            if yy < fade:
                a = int(255 * (1 - yy / fade))
            elif yy > CANVAS_HEIGHT - fade:
                a = int(255 * ((yy - (CANVAS_HEIGHT - fade)) / fade))
            else:
                a = 0
            ov_draw.line([(0, yy), (CANVAS_WIDTH, yy)], fill=(18, 25, 36, a))
        canvas = Image.alpha_composite(canvas, overlay)
        draw = ImageDraw.Draw(canvas)

        # ── 1) LOGO ──────────────────────────────────────────────────────────
        logo_path = os.path.join("assets", "logo.png")
        if os.path.exists(logo_path):
            logo = Image.open(logo_path).convert("RGBA") \
                        .resize((LOGO_SIZE, LOGO_SIZE), Image.LANCZOS)
            canvas.paste(logo, ((CANVAS_WIDTH - LOGO_SIZE) // 2, y), logo)
        y += LOGO_SIZE + GAP

        # ── 2) BAŞLIK ────────────────────────────────────────────────────────
        for line in title_lines:
            bbox = draw.textbbox((0, 0), line, font=title_font)
            draw.text(((CANVAS_WIDTH - (bbox[2] - bbox[0])) // 2, y),
                      line, font=title_font, fill=TEXT_COLOR)
            y += (bbox[3] - bbox[1]) + 30
        y = y - 30 + GAP   # son satırın fazla spacing'ini geri al + GAP

        # ── 3) FOTOĞRAF (sabit kutu, contain, kutu içinde ortada) ────────────
        if image_path and os.path.exists(image_path):
            img = Image.open(image_path).convert("RGB")
            ir = img.width / img.height
            br = PHOTO_BOX_W / photo_box_h
            if ir > br:
                n_w, n_h = PHOTO_BOX_W, int(PHOTO_BOX_W / ir)
            else:
                n_h, n_w = photo_box_h, int(photo_box_h * ir)
            img = img.resize((n_w, n_h), Image.LANCZOS)
            img_x = MARGIN_X + (PHOTO_BOX_W - n_w) // 2
            img_y = y + (photo_box_h - n_h) // 2
            canvas.paste(img, (img_x, img_y))
        y += photo_box_h + (GAP if has_body else 0)

        # ── 4) AÇIKLAMA ──────────────────────────────────────────────────────
        for line in body_lines:
            bbox = draw.textbbox((0, 0), line, font=body_font)
            draw.text(((CANVAS_WIDTH - (bbox[2] - bbox[0])) // 2, y),
                      line, font=body_font, fill=TEXT_COLOR)
            y += (bbox[3] - bbox[1]) + 24

        # ── Kaydet ───────────────────────────────────────────────────────────
        canvas.convert("RGB").save(output_path, format="PNG", optimize=True)
        return output_path

    except Exception as e:
        st.error(f"Hata: {e}")
        import traceback
        st.code(traceback.format_exc())
        return None


# ── STREAMLIT ARAYÜZÜ ────────────────────────────────────────────────────────
st.set_page_config(page_title="Story Asistanım", page_icon="📸", layout="centered")
st.title("📸 Story Asistanım")
st.markdown("Fotoğrafı yükle, metinleri yaz, saniyeler içinde o muhteşem şablonu indir!")

col1, col2 = st.columns(2)
with col1:
    title_text = st.text_input("📝 Başlık (Marka / Model / Konu)", "ÖZEL KAMPANYA")
with col2:
    body_text = st.text_area("📄 Alt Metin (Fiyat / Detay)",
                             "Sadece bu hafta geçerlidir!\nFiyat: 1.250.000 TL")

uploaded_file = st.file_uploader("⬆️ Araç/Haber Görselini Yükle",
                                 type=['jpg', 'jpeg', 'png'])

if st.button("🎨 Şablonu Oluştur", type="primary", use_container_width=True):
    if uploaded_file is None:
        st.warning("Lütfen bir görsel yükleyin!")
    else:
        with st.spinner("4K Şablon hazırlanıyor..."):
            temp_dir = tempfile.mkdtemp()
            input_path = os.path.join(temp_dir, "input_img.png")
            output_path = os.path.join(temp_dir, "story_card_4k.png")

            with open(input_path, "wb") as f:
                f.write(uploaded_file.getbuffer())

            result_path = create_social_card(f"{title_text}\n{body_text}",
                                             input_path, output_path)

            if result_path:
                st.success("4K Şablon başarıyla oluşturuldu!")
                with open(result_path, "rb") as f:
                    b64_image = base64.b64encode(f.read()).decode()

                st.markdown("""
                <div style="background-color:#1E293B; padding:15px; border-radius:10px;
                            border:1px solid #334155; margin-bottom:20px;">
                    <p style="color:#FBBF24; font-weight:bold; margin:0 0 5px 0;">
                        📱 iPhone Kullanıcıları İçin Önemli Not:</p>
                    <p style="color:#E2E8F0; font-size:14px; margin:0;">
                    Görselin üzerine parmağınızla <b>basılı tutun</b> →
                    <b>"Fotoğrafa Kaydet"</b>.</p>
                </div>
                """, unsafe_allow_html=True)

                st.markdown(
                    f'<img src="data:image/png;base64,{b64_image}" '
                    f'style="width:100%; border-radius:15px; '
                    f'box-shadow: 0 4px 15px rgba(0,0,0,0.5);" alt="Story Kart">',
                    unsafe_allow_html=True)
