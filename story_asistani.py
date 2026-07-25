import os
import re
import base64
import tempfile
import streamlit as st
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

# ── Ayarlar (4K Story — o botun 1080 ayarlarının 2x ölçeklenmiş hali) ────────
CANVAS_WIDTH = 2160
CANVAS_HEIGHT = 3840
BG_COLOR_RGBA = (18, 25, 36, 255)
TEXT_COLOR = (255, 255, 255)

FONT_BOLD_PATH = os.path.join("assets", "Roboto-Bold.ttf")
FONT_REG_PATH = os.path.join("assets", "Roboto-Regular.ttf")

# Layout sabitleri (1080'deki değerlerin 2x'i)
LOGO_SIZE = 240          # o bot: 120
IMAGE_BOX_H = 1520       # o bot: 760
GAP = 96                 # o bot: 48
MARGIN = 240             # o bot: 120 (sol/sağ pay)
BLUR_RADIUS = 60         # o bot: 30
OVERLAY_ALPHA = 120      # o bot: 120 (ölçeklenmez)
SAFE_MARGIN = 120        # taşma emniyeti

# Auto-shrink font aralıkları
TITLE_FONT_START, TITLE_FONT_MIN, TITLE_MAX_H = 124, 64, 420
BODY_FONT_START, BODY_FONT_MIN, BODY_MAX_H = 80, 44, 820


# ── Türkçe Büyük Harf (o bot .upper() kullanıyordu, bu daha doğru) ───────────
def turkish_upper(text: str) -> str:
    return text.replace('i', 'İ').replace('ı', 'I').upper()


def _get_font(size: int, bold: bool = False):
    path = FONT_BOLD_PATH if bold else FONT_REG_PATH
    if not os.path.exists(path):
        st.error(f"Font bulunamadı: {path}. Lütfen assets klasörüne fontları koy.")
        return ImageFont.load_default()
    return ImageFont.truetype(path, size)


def _wrap_text(draw, text, font, max_width):
    words = text.split()
    lines, current = [], ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if (bbox[2] - bbox[0]) <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _measure(draw, lines, font, spacing):
    h = 0
    for ln in lines:
        b = draw.textbbox((0, 0), ln, font=font)
        h += (b[3] - b[1])
    return h + max(0, len(lines) - 1) * spacing


def _fit_cover(img, target_w, target_h):
    """Arka plan için: kutuyu tam doldur, taşanları kırp (o botun mantığı)."""
    return ImageOps.fit(img, (target_w, target_h),
                        method=Image.LANCZOS, centering=(0.5, 0.5))


def _fit_contain(img, max_w, max_h):
    """Ana görsel için: oranı koru, kutunun içine sığdır (o botun mantığı)."""
    ratio = min(max_w / img.width, max_h / img.height)
    n_w = max(1, int(img.width * ratio))
    n_h = max(1, int(img.height * ratio))
    return img.resize((n_w, n_h), Image.LANCZOS)


def _fit_text_in_box(draw, text, size_start, size_min,
                     max_width, max_height, bold, spacing):
    """Metin kutuya sığmazsa fontu 4'er küçült (senin 'uzun metin küçülsün' isteğin)."""
    size = size_start
    while size >= size_min:
        font = _get_font(size, bold=bold)
        lines = _wrap_text(draw, text, font, max_width)
        if _measure(draw, lines, font, spacing) <= max_height:
            return lines, font, spacing
        size -= 4
    font = _get_font(size_min, bold=bold)
    lines = _wrap_text(draw, text, font, max_width)
    return lines, font, spacing


def create_social_card(post_text: str, image_path: str, output_path: str) -> str:
    try:
        # ── Metni hazırla ─────────────────────────────────────────────────────
        lines = [ln.strip() for ln in (post_text or "").split("\n") if ln.strip()]
        title = lines[0] if lines else "OTOXTRA HABER"
        title = re.sub(r"[^a-zA-Z0-9ÇĞİÖŞÜçğıöşü\s]", "", title).strip()
        title = turkish_upper(title)
        body = "\n".join(lines[1:]) if len(lines) > 1 else ""

        dummy_draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        max_text_width = CANVAS_WIDTH - MARGIN

        title_lines, title_font, t_sp = _fit_text_in_box(
            dummy_draw, title, TITLE_FONT_START, TITLE_FONT_MIN,
            max_text_width, TITLE_MAX_H, bold=True, spacing=20)
        title_h = _measure(dummy_draw, title_lines, title_font, t_sp)

        if body.strip():
            body_lines, body_font, b_sp = _fit_text_in_box(
                dummy_draw, body, BODY_FONT_START, BODY_FONT_MIN,
                max_text_width, BODY_MAX_H, bold=False, spacing=16)
            body_h = _measure(dummy_draw, body_lines, body_font, b_sp)
        else:
            body_lines, body_font, b_sp, body_h = [], None, 16, 0

        # ── Blok yüksekliği + taşma emniyeti ─────────────────────────────────
        has_body = body_h > 0
        gap_count = 2 + (1 if has_body else 0)
        image_box_h = IMAGE_BOX_H
        total_h = LOGO_SIZE + title_h + image_box_h + body_h + gap_count * GAP

        available = CANVAS_HEIGHT - 2 * SAFE_MARGIN
        if total_h > available:                       # çok uzun içerik → fotoğraftan kıs
            image_box_h = max(800, image_box_h - (total_h - available))
            total_h = LOGO_SIZE + title_h + image_box_h + body_h + gap_count * GAP

        y = max(SAFE_MARGIN, (CANVAS_HEIGHT - total_h) // 2)   # BLOĞU ORTALA

        # ── Canvas + blur arka plan (o botun hafif blur'u) ───────────────────
        canvas = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), BG_COLOR_RGBA)
        if image_path and os.path.exists(image_path):
            try:
                src = Image.open(image_path).convert("RGB")
                bg = _fit_cover(src, CANVAS_WIDTH, CANVAS_HEIGHT)
                bg = bg.filter(ImageFilter.GaussianBlur(BLUR_RADIUS))
                canvas.paste(bg, (0, 0))
            except Exception as e:
                st.warning(f"Blur arka plan hazırlanamadı: {e}")

        # Düz karartma overlay (o botun mantığı — fade yerine tek katman)
        overlay = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT),
                            (18, 25, 36, OVERLAY_ALPHA))
        canvas = Image.alpha_composite(canvas, overlay)
        draw = ImageDraw.Draw(canvas)

        # ── 1) LOGO ──────────────────────────────────────────────────────────
        logo_path = os.path.join("assets", "logo.png")
        if os.path.exists(logo_path):
            try:
                logo = Image.open(logo_path).convert("RGBA") \
                            .resize((LOGO_SIZE, LOGO_SIZE), Image.LANCZOS)
                canvas.paste(logo, ((CANVAS_WIDTH - LOGO_SIZE) // 2, y), logo)
            except Exception as e:
                st.warning(f"Logo işlenemedi: {e}")
        y += LOGO_SIZE + GAP

        # ── 2) BAŞLIK (gölgeli metin — o botun dokunuşu) ─────────────────────
        for ln in title_lines:
            b = draw.textbbox((0, 0), ln, font=title_font)
            lw, lh = b[2] - b[0], b[3] - b[1]
            x = (CANVAS_WIDTH - lw) // 2
            draw.text((x + 4, y + 4), ln, font=title_font, fill=(0, 0, 0, 140))  # gölge
            draw.text((x, y), ln, font=title_font, fill=TEXT_COLOR)
            y += lh + t_sp
        y += GAP - t_sp

        # ── 3) FOTOĞRAF (yuvarlatılmış köşe + yumuşak gölge) ─────────────────
        img_top = y
        if image_path and os.path.exists(image_path):
            try:
                src = Image.open(image_path).convert("RGB")
                main_img = _fit_contain(src, CANVAS_WIDTH - MARGIN, image_box_h)
                iw, ih = main_img.size
                img_x = (CANVAS_WIDTH - iw) // 2
                img_y = img_top + (image_box_h - ih) // 2

                # Yumuşak gölge
                shadow = Image.new("RGBA", (iw + 24, ih + 24), (0, 0, 0, 0))
                sdraw = ImageDraw.Draw(shadow)
                sdraw.rounded_rectangle((12, 12, iw + 12, ih + 12),
                                        radius=48, fill=(0, 0, 0, 90))
                canvas.alpha_composite(shadow, dest=(img_x - 12, img_y - 12))

                # Yuvarlatılmış köşe maskesi
                mask = Image.new("L", (iw, ih), 0)
                ImageDraw.Draw(mask).rounded_rectangle((0, 0, iw, ih),
                                                       radius=40, fill=255)
                canvas.paste(main_img.convert("RGBA"), (img_x, img_y), mask)
            except Exception as e:
                st.warning(f"Ana görsel işlenemedi: {e}")
        y += image_box_h + (GAP if has_body else 0)

        # ── 4) AÇIKLAMA (gölgeli metin) ──────────────────────────────────────
        for ln in body_lines:
            b = draw.textbbox((0, 0), ln, font=body_font)
            lw, lh = b[2] - b[0], b[3] - b[1]
            x = (CANVAS_WIDTH - lw) // 2
            draw.text((x + 3, y + 3), ln, font=body_font, fill=(0, 0, 0, 130))  # gölge
            draw.text((x, y), ln, font=body_font, fill=TEXT_COLOR)
            y += lh + b_sp

        # ── Kaydet (o botun PNG sıkıştırma ayarı) ────────────────────────────
        final_img = canvas.convert("RGB")
        lower = (output_path or "").lower()
        if lower.endswith(".png"):
            final_img.save(output_path, format="PNG", optimize=True, compress_level=4)
        else:
            final_img.save(output_path, format="JPEG", quality=95,
                           optimize=True, subsampling=0)
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
