import os
import re
import tempfile
import streamlit as st
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ── Ayarlar ───────────────────────────────────────────────────────────────────
# 4K Dikey Çözünürlük (2160x3840)
CANVAS_WIDTH = 2160
CANVAS_HEIGHT = 3840
BG_COLOR_RGBA = (18, 25, 36, 255)
TEXT_COLOR = (255, 255, 255)

# Projenin assets klasöründen fontları okuyoruz
FONT_BOLD_PATH = os.path.join("assets", "Roboto-Bold.ttf")
FONT_REG_PATH = os.path.join("assets", "Roboto-Regular.ttf")

def _get_font(size: int, bold: bool = False):
    path = FONT_BOLD_PATH if bold else FONT_REG_PATH
    if not os.path.exists(path):
        st.error(f"Font bulunamadı: {path}. Lütfen assets klasörüne fontları koy.")
        return ImageFont.load_default()
    return ImageFont.truetype(path, size)

def _wrap_text(draw, text, font, max_width):
    words = text.split()
    lines = []
    current_line = ""
    for word in words:
        test_line = f"{current_line} {word}".strip()
        bbox = draw.textbbox((0, 0), test_line, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current_line = test_line
        else:
            if current_line: lines.append(current_line)
            current_line = word
    if current_line: lines.append(current_line)
    return lines

def create_social_card(post_text: str, image_path: str, output_path: str) -> str:
    try:
        lines = [ln.strip() for ln in post_text.split("\n") if ln.strip()]
        title = lines[0] if lines else "OTOXTRA HABER"
        title = re.sub(r'[^\w\s]', '', title).strip().upper()
        body = "\n".join(lines[1:]) if len(lines) > 1 else ""

        dummy_img = Image.new("RGB", (1, 1))
        dummy_draw = ImageDraw.Draw(dummy_img)

        # 4K için font boyutlarını ölçekle (2x)
        font_title = _get_font(110, bold=True)
        title_lines = _wrap_text(dummy_draw, title, font_title, CANVAS_WIDTH - 320)
        title_h = sum([(dummy_draw.textbbox((0,0), line, font=font_title)[3]) for line in title_lines]) + (len(title_lines)-1)*30

        font_body = _get_font(70, bold=False)
        body_lines = _wrap_text(dummy_draw, body, font_body, CANVAS_WIDTH - 320)
        body_h = sum([(dummy_draw.textbbox((0,0), line, font=font_body)[3]) for line in body_lines]) + (len(body_lines)-1)*24

        logo_h = 240
        img_h = 1400
        gap = 80

        total_h = logo_h + gap + title_h + gap + img_h + gap + body_h
        y_cursor = (CANVAS_HEIGHT - total_h) // 2

        canvas = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), BG_COLOR_RGBA)
        
        if image_path and os.path.exists(image_path):
            img = Image.open(image_path).convert("RGB")
            img_ratio = img.width / img.height
            canvas_ratio = CANVAS_WIDTH / CANVAS_HEIGHT
            
            if img_ratio > canvas_ratio:
                b_h = CANVAS_HEIGHT
                b_w = int(b_h * img_ratio)
            else:
                b_w = CANVAS_WIDTH
                b_h = int(b_w / img_ratio)
                
            blur_img = img.resize((b_w, b_h), Image.LANCZOS)
            blur_img = blur_img.filter(ImageFilter.GaussianBlur(140))
            
            left = (b_w - CANVAS_WIDTH) // 2
            top = (b_h - CANVAS_HEIGHT) // 2
            blur_img = blur_img.crop((left, top, left + CANVAS_WIDTH, top + CANVAS_HEIGHT))
            canvas.paste(blur_img, (0, 0))

        overlay = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), (0,0,0,0))
        draw_overlay = ImageDraw.Draw(overlay)
        fade_dist = 1200
        
        for y in range(CANVAS_HEIGHT):
            if y < fade_dist:
                alpha = int(255 * (1 - y / fade_dist))
            elif y > CANVAS_HEIGHT - fade_dist:
                alpha = int(255 * ((y - (CANVAS_HEIGHT - fade_dist)) / fade_dist))
            else:
                alpha = 0
            draw_overlay.line([(0, y), (CANVAS_WIDTH, y)], fill=(18, 25, 36, alpha))
            
        canvas = Image.alpha_composite(canvas, overlay)
        draw = ImageDraw.Draw(canvas)

        logo_path = os.path.join("assets", "logo.png")
        if os.path.exists(logo_path):
            logo = Image.open(logo_path).convert("RGBA")
            logo = logo.resize((logo_h, logo_h), Image.LANCZOS)
            logo_x = (CANVAS_WIDTH - logo_h) // 2
            canvas.paste(logo, (logo_x, y_cursor), logo)
        y_cursor += logo_h + gap

        for line in title_lines:
            bbox = draw.textbbox((0,0), line, font=font_title)
            line_w = bbox[2] - bbox[0]
            x = (CANVAS_WIDTH - line_w) // 2
            draw.text((x, y_cursor), line, font=font_title, fill=TEXT_COLOR)
            y_cursor += bbox[3] + 30
        y_cursor += gap - 30

        img_y = y_cursor
        if image_path and os.path.exists(image_path):
            img = Image.open(image_path).convert("RGB")
            img_ratio = img.width / img.height
            target_ratio = 2000 / img_h
            
            if img_ratio > target_ratio: 
                n_w = 2000
                n_h = int(2000 / img_ratio)
            else: 
                n_h = img_h
                n_w = int(img_h * img_ratio)
                
            img = img.resize((n_w, n_h), Image.LANCZOS)
            img_x = (CANVAS_WIDTH - n_w) // 2
            canvas.paste(img, (img_x, img_y + (img_h - n_h)//2))
        y_cursor += img_h + gap

        for line in body_lines:
            bbox = draw.textbbox((0,0), line, font=font_body)
            line_w = bbox[2] - bbox[0]
            x = (CANVAS_WIDTH - line_w) // 2
            draw.text((x, y_cursor), line, font=font_body, fill=TEXT_COLOR)
            y_cursor += bbox[3] + 24

        # PNG formatında ve maksimum kalitede kaydet (4K için şeffaflık desteği)
        canvas.save(output_path, format="PNG", quality=100)
        return output_path

    except Exception as e:
        st.error(f"Hata: {e}")
        return None

# ── STREAMLIT ARAYÜZÜ ────────────────────────────────────────────────────────
st.set_page_config(page_title="Story Asistanım", page_icon="📸", layout="centered")
st.title("📸 Story Asistanım")
st.markdown("Fotoğrafı yükle, metinleri yaz, saniyeler içinde o muhteşem şablonu indir!")

col1, col2 = st.columns(2)
with col1:
    title_text = st.text_input("📝 Başlık (Marka / Model / Konu)", "ÖZEL KAMPANYA")
with col2:
    body_text = st.text_area("📄 Alt Metin (Fiyat / Detay)", "Sadece bu hafta geçerlidir!\nFiyat: 1.250.000 TL")

uploaded_file = st.file_uploader("⬆️ Araç/Haber Görselini Yükle", type=['jpg', 'jpeg', 'png'])

if st.button("🎨 Şablonu Oluştur", type="primary", use_container_width=True):
    if uploaded_file is None:
        st.warning("Lütfen bir görsel yükleyin!")
    else:
        with st.spinner("Muhteşem şablon hazırlanıyor..."):
            # Geçici dosyalar
            temp_dir = tempfile.mkdtemp()
            input_path = os.path.join(temp_dir, "input_img.png")
            output_path = os.path.join(temp_dir, "story_card.png")
            
            with open(input_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            # Metni birleştir
            full_text = f"{title_text}\n{body_text}"
            
            # Kartı oluştur
            result_path = create_social_card(full_text, input_path, output_path)
            
            if result_path:
                st.success("Şablon başarıyla oluşturuldu!")
                st.image(result_path, caption="Önizleme", use_column_width=True)
                
                with open(result_path, "rb") as f:
                    st.download_button(
                        label="📥 Görseli İndir (4K PNG)",
                        data=f,
                        file_name="story_kart_4k.png",
                        mime="image/png",
                        use_container_width=True
                    )
