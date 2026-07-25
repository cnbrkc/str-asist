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

# ── SABİT LAYOUT ZONE'LARI (piksel cinsinden) ────────────────────────────────
# Her şey bu sabit pozisyonlarda durur. İçerik değişse bile yer KAYMAZ.
MARGIN_X = 160          # Sol/sağ margin

LOGO_SIZE = 220         # Logo kare boyutu
LOGO_Y = 200            # Logo'nun üst kenarının Y pozisyonu

TITLE_Y = 520           # Başlığın üst kenarının Y pozisyonu
TITLE_MAX_H = 400       # Başlık için ayrılan maksimum yükseklik

PHOTO_Y = 1050          # Fotoğrafın üst kenarının Y pozisyonu
PHOTO_H = 1500          # Fotoğrafın sabit yüksekliği
PHOTO_W = CANVAS_WIDTH - (MARGIN_X * 2)  # 1840px sabit genişlik

BODY_Y = 2750           # Açıklama metninin üst kenarının Y pozisyonu
BODY_MAX_H = 900        # Açıklama için ayrılan maksimum yükseklik


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
    """Metni verilen genişliğe göre satırlara böler."""
    words = text.split()
    lines = []
    current_line = ""
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


def _fit_text_in_box(draw, text, font_size_start, font_size_min,
                     max_width, max_height, bold=False, line_spacing=28):
    """
    Metni verilen kutuya sığdırır. Sığmazsa font boyutunu 4'er küçültür.
    Returns: (lines, font, total_height)
    """
    size = font_size_start
    while size >= font_size_min:
        font = _get_font(size, bold=bold)
        lines = _wrap_text(draw, text, font, max_width)
        total_h = 0
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            total_h += (bbox[3] - bbox[1])
        total_h += (len(lines) - 1) * line_spacing

        if total_h <= max_height:
            return lines, font, total_h
        size -= 4

    # Minimum boyutta bile sığmıyorsa son halini döndür
    font = _get_font(font_size_min, bold=bold)
    lines = _wrap_text(draw, text, font, max_width)
    total_h = 0
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        total_h += (bbox[3] - bbox[1])
    total_h += (len(lines) - 1) * line_spacing
    return lines, font, total_h


def create_social_card(post_text: str, image_path: str, output_path: str) -> str:
    try:
        lines = [ln.strip() for ln in post_text.split("\n") if ln.strip()]
        title = lines[0] if lines else "OTOXTRA HABER"
        title = re.sub(r'[^a-zA-Z0-9ÇĞİÖŞÜçğıöşü\s]', '', title).strip()
        title = turkish_upper(title)
        body = "\n".join(lines[1:]) if len(lines) > 1 else ""

        # ── Canvas oluştur ────────────────────────────────────────────────────
        canvas = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), BG_COLOR_RGBA)

        # ── Arka plan: Bulanık fotoğraf (cover mod) ──────────────────────────
        if image_path and os.path.exists(image_path):
            img_raw = Image.open(image_path).convert("RGB")
            img_ratio = img_raw.width / img_raw.height
            canvas_ratio = CANVAS_WIDTH / CANVAS_HEIGHT

            if img_ratio > canvas_ratio:
                b_h = CANVAS_HEIGHT
                b_w = int(b_h * img_ratio)
            else:
                b_w = CANVAS_WIDTH
                b_h = int(b_w / img_ratio)

            blur_img = img_raw.resize((b_w, b_h), Image.LANCZOS)
            blur_img = blur_img.filter(ImageFilter.GaussianBlur(140))

            left = (b_w - CANVAS_WIDTH) // 2
            top = (b_h - CANVAS_HEIGHT) // 2
            blur_img = blur_img.crop((left, top, left + CANVAS_WIDTH, top + CANVAS_HEIGHT))
            canvas.paste(blur_img, (0, 0))

        # ── Karartma overlay (üst ve alt fade) ───────────────────────────────
        overlay = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 0))
        draw_ov = ImageDraw.Draw(overlay)
        fade_dist = 1200
        for y in range(CANVAS_HEIGHT):
            if y < fade_dist:
                alpha = int(255 * (1 - y / fade_dist))
            elif y > CANVAS_HEIGHT - fade_dist:
                alpha = int(255 * ((y - (CANVAS_HEIGHT - fade_dist)) / fade_dist))
            else:
                alpha = 0
            draw_ov.line([(0, y), (CANVAS_WIDTH, y)], fill=(18, 25, 36, alpha))
        canvas = Image.alpha_composite(canvas, overlay)

        draw = ImageDraw.Draw(canvas)
        content_width = CANVAS_WIDTH - (MARGIN_X * 2)

        # ── 1) LOGO — sabit pozisyon, yatay ortada ───────────────────────────
        logo_path = os.path.join("assets", "logo.png")
        if os.path.exists(logo_path):
            logo = Image.open(logo_path).convert("RGBA")
            logo = logo.resize((LOGO_SIZE, LOGO_SIZE), Image.LANCZOS)
            logo_x = (CANVAS_WIDTH - LOGO_SIZE) // 2
            canvas.paste(logo, (logo_x, LOGO_Y), logo)

        # ── 2) BAŞLIK — sabit zone, dikey ortada, sığmazsa küçülür ──────────
        title_lines, title_font, title_total_h = _fit_text_in_box(
            draw, title,
            font_size_start=110,
            font_size_min=60,
            max_width=content_width,
            max_height=TITLE_MAX_H,
            bold=True,
            line_spacing=30
        )
        # Zone'un dikey ortasına yerleştir
        title_block_y = TITLE_Y + (TITLE_MAX_H - title_total_h) // 2
        y_cur = title_block_y
        for line in title_lines:
            bbox = draw.textbbox((0, 0), line, font=title_font)
            line_w = bbox[2] - bbox[0]
            x = (CANVAS_WIDTH - line_w) // 2
            draw.text((x, y_cur), line, font=title_font, fill=TEXT_COLOR)
            y_cur += (bbox[3] - bbox[1]) + 30

        # ── 3) FOTOĞRAF — sabit kutu, "contain" mod, tam ortada ─────────────
        if image_path and os.path.exists(image_path):
            img = Image.open(image_path).convert("RGB")
            img_ratio = img.width / img.height
            box_ratio = PHOTO_W / PHOTO_H

            if img_ratio > box_ratio:
                # Geniş fotoğraf → genişliğe sığdır
                n_w = PHOTO_W
                n_h = int(PHOTO_W / img_ratio)
            else:
                # Uzun fotoğraf → yüksekliğe sığdır
                n_h = PHOTO_H
                n_w = int(PHOTO_H * img_ratio)

            img = img.resize((n_w, n_h), Image.LANCZOS)

            # Kutunun tam ortasına yerleştir
            img_x = MARGIN_X + (PHOTO_W - n_w) // 2
            img_y = PHOTO_Y + (PHOTO_H - n_h) // 2
            canvas.paste(img, (img_x, img_y))

        # ── 4) AÇIKLAMA METNİ — sabit zone, dikey ortada, sığmazsa küçülür ──
        if body.strip():
            body_lines, body_font, body_total_h = _fit_text_in_box(
                draw, body,
                font_size_start=70,
                font_size_min=40,
                max_width=content_width,
                max_height=BODY_MAX_H,
                bold=False,
                line_spacing=24
            )
            # Zone'un dikey ortasına yerleştir
            body_block_y = BODY_Y + (BODY_MAX_H - body_total_h) // 2
            y_cur = body_block_y
            for line in body_lines:
                bbox = draw.textbbox((0, 0), line, font=body_font)
                line_w = bbox[2] - bbox[0]
                x = (CANVAS_WIDTH - line_w) // 2
                draw.text((x, y_cur), line, font=body_font, fill=TEXT_COLOR)
                y_cur += (bbox[3] - bbox[1]) + 24

        # ── Kaydet (4K PNG) ──────────────────────────────────────────────────
        canvas = canvas.convert("RGB")
        canvas.save(output_path, format="PNG", optimize=True)
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

            full_text = f"{title_text}\n{body_text}"
            result_path = create_social_card(full_text, input_path, output_path)

            if result_path:
                st.success("4K Şablon başarıyla oluşturuldu!")

                with open(result_path, "rb") as f:
                    image_bytes = f.read()
                b64_image = base64.b64encode(image_bytes).decode()

                st.markdown("""
                <div style="background-color:#1E293B; padding:15px; border-radius:10px;
                            border:1px solid #334155; margin-bottom:20px;">
                    <p style="color:#FBBF24; font-weight:bold; margin:0 0 5px 0;">
                        📱 iPhone Kullanıcıları İçin Önemli Not:</p>
                    <p style="color:#E2E8F0; font-size:14px; margin:0;">
                    Aşağıdaki görselin üzerine parmağınızla <b>basılı tutun</b> ve
                    açılan menüden <b>"Fotoğrafa Kaydet"</b> seçeneğine dokunun.
                    </p>
                </div>
                """, unsafe_allow_html=True)

                st.markdown(
                    f'<img src="data:image/png;base64,{b64_image}" '
                    f'style="width:100%; border-radius:15px; '
                    f'box-shadow: 0 4px 15px rgba(0,0,0,0.5);" alt="Story Kart">',
                    unsafe_allow_html=True
                )
