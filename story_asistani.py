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


CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1920

BG_COLOR_RGBA = (18, 25, 36, 255)
TEXT_COLOR = (255, 255, 255)

FONT_BOLD_PATH = os.path.join(get_project_root(), "assets", "Roboto-Bold.ttf")
FONT_REG_PATH = os.path.join(get_project_root(), "assets", "Roboto-Regular.ttf")


def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = FONT_BOLD_PATH if bold else FONT_REG_PATH
    if not os.path.exists(path):
        log(f"Font bulunamadi: {path}. Varsayilan kullaniliyor.", "WARNING")
        return ImageFont.load_default()
    return ImageFont.truetype(path, size)


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list:
    words = text.split()
    lines = []
    current_line = ""
    
    for word in words:
        test_line = f"{current_line} {word}".strip()
        bbox = draw.textbbox((0, 0), test_line, font=font)
        
        if (bbox[2] - bbox[0]) <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
                current_line = ""
            
            bbox_word = draw.textbbox((0, 0), word, font=font)
            if (bbox_word[2] - bbox_word[0]) > max_width:
                temp_line = ""
                for char in word:
                    test_char = temp_line + char
                    bbox_c = draw.textbbox((0, 0), test_char, font=font)
                    if (bbox_c[2] - bbox_c[0]) <= max_width:
                        temp_line = test_char
                    else:
                        if temp_line:
                            lines.append(temp_line)
                        temp_line = char
                current_line = temp_line
            else:
                current_line = word
                
    if current_line:
        lines.append(current_line)
    return lines


def _fit_cover(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    return ImageOps.fit(img, (target_w, target_h), method=Image.LANCZOS, centering=(0.5, 0.5))


def _fit_contain(img: Image.Image, max_w: int, max_h: int) -> Image.Image:
    ratio = min(max_w / img.width, max_h / img.height)
    n_w = max(1, int(img.width * ratio))
    n_h = max(1, int(img.height * ratio))
    return img.resize((n_w, n_h), Image.LANCZOS)


def _prepare_text(post_text: str):
    lines = [ln.strip() for ln in (post_text or "").split("\n") if ln.strip()]
    title = lines[0] if lines else ""
    if title:
        title = re.sub(r"[^\w\s]", "", title).strip().upper()
    body = "\n".join(lines[1:]) if len(lines) > 1 else ""
    return title, body


def create_social_card(post_text: str, image_path: str, output_path: str) -> str:
    """
    Story kart üretimi — DİNAMİK ORTALAMA ve FERAH TASARIM
    """
    try:
        title, body = _prepare_text(post_text)

        max_text_width = CANVAS_WIDTH - 120
        logo_size = 120
        gap = 80  # ★ ARALIKLARI BURADAN 80 PX YAPTIK, DAHA FERAH!
        max_img_h = 760

        logo_path = os.path.join(get_project_root(), "assets", "logo.png")
        has_logo = os.path.exists(logo_path)

        dummy_img = Image.new("RGB", (1, 1))
        dummy_draw = ImageDraw.Draw(dummy_img)

        title_font_size = 62
        body_font_size = 40
        
        while title_font_size >= 30 or body_font_size >= 24:
            font_title = _get_font(title_font_size, bold=True)
            font_body = _get_font(body_font_size, bold=False)
            
            title_lines = _wrap_text(dummy_draw, title, font_title, max_text_width) if title else []
            body_lines = _wrap_text(dummy_draw, body, font_body, max_text_width) if body else []

            title_h = 0
            for ln in title_lines:
                b = dummy_draw.textbbox((0, 0), ln, font=font_title)
                title_h += (b[3] - b[1]) + 10
            if title_lines: title_h -= 10

            body_h = 0
            for ln in body_lines:
                b = dummy_draw.textbbox((0, 0), ln, font=font_body)
                body_h += (b[3] - b[1]) + 8
            if body_lines: body_h -= 8

            other_h = 0
            if has_logo: other_h += logo_size + gap
            if title_lines: other_h += title_h + gap
            if body_lines: other_h += body_h + gap

            available_h = CANVAS_HEIGHT - 80 - other_h
            dynamic_max_img_h = min(max_img_h, max(100, available_h))

            elements = []
            if has_logo: elements.append(("logo", logo_size))
            if title_lines: elements.append(("title", title_h))
            elements.append(("image", dynamic_max_img_h))
            if body_lines: elements.append(("body", body_h))
            
            total_h = sum(h for _, h in elements) + gap * (len(elements) - 1)

            if total_h <= CANVAS_HEIGHT - 80:
                break
            
            if title_font_size > 30: title_font_size -= 2
            if body_font_size > 24: body_font_size -= 2
            
            if title_font_size <= 30 and body_font_size <= 24:
                break

        main_img = None
        img_actual_h = 0
        if image_path and os.path.exists(image_path):
            try:
                src = Image.open(image_path).convert("RGB")
                main_img = _fit_contain(src, CANVAS_WIDTH - 80, dynamic_max_img_h)
                img_actual_h = main_img.height
            except Exception as e:
                log(f"Ana gorsel islenemedi: {e}", "WARNING")

        elements = []
        if has_logo: elements.append(("logo", logo_size))
        if title_lines: elements.append(("title", title_h))
        if main_img is not None: elements.append(("image", img_actual_h))
        if body_lines: elements.append(("body", body_h))

        num_gaps = max(0, len(elements) - 1)
        total_h = sum(h for _, h in elements) + gap * num_gaps
        y_cursor = max(40, (CANVAS_HEIGHT - total_h) // 2)

        canvas = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), BG_COLOR_RGBA)

        if image_path and os.path.exists(image_path):
            try:
                src = Image.open(image_path).convert("RGB")
                bg = _fit_cover(src, CANVAS_WIDTH, CANVAS_HEIGHT)
                bg = bg.filter(ImageFilter.GaussianBlur(30))
                canvas.paste(bg, (0, 0))
            except Exception as e:
                log(f"Blur arka plan hazirlanamadi: {e}", "WARNING")

        overlay = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), (18, 25, 36, 120))
        canvas = Image.alpha_composite(canvas, overlay)
        draw = ImageDraw.Draw(canvas)

        for idx, (elem_type, _) in enumerate(elements):
            if idx > 0:
                y_cursor += gap

            if elem_type == "logo":
                try:
                    logo = Image.open(logo_path).convert("RGBA")
                    logo = logo.resize((logo_size, logo_size), Image.LANCZOS)
                    logo_x = (CANVAS_WIDTH - logo_size) // 2
                    canvas.paste(logo, (logo_x, y_cursor), logo)
                except Exception as e:
                    log(f"Logo islenemedi: {e}", "WARNING")
                y_cursor += logo_size

            elif elem_type == "title":
                for ln in title_lines:
                    b = draw.textbbox((0, 0), ln, font=font_title)
                    lw = b[2] - b[0]
                    lh = b[3] - b[1]
                    x = (CANVAS_WIDTH - lw) // 2 - b[0]
                    draw.text((x + 2, y_cursor + 2), ln, font=font_title, fill=(0, 0, 0, 140))
                    draw.text((x, y_cursor), ln, font=font_title, fill=TEXT_COLOR)
                    y_cursor += lh + 10
                y_cursor -= 10

            elif elem_type == "image":
                img_w, img_h = main_img.size
                img_x = (CANVAS_WIDTH - img_w) // 2

                mask = Image.new("L", (img_w, img_h), 0)
                mdraw = ImageDraw.Draw(mask)
                mdraw.rounded_rectangle((0, 0, img_w, img_h), radius=20, fill=255)

                shadow = Image.new("RGBA", (img_w + 12, img_h + 12), (0, 0, 0, 0))
                sdraw = ImageDraw.Draw(shadow)
                sdraw.rounded_rectangle((6, 6, img_w + 6, img_h + 6), radius=24, fill=(0, 0, 0, 90))
                canvas.alpha_composite(shadow, dest=(img_x - 6, y_cursor - 6))

                main_rgba = main_img.convert("RGBA")
                canvas.paste(main_rgba, (img_x, y_cursor), mask)
                y_cursor += img_h

            elif elem_type == "body":
                for ln in body_lines:
                    b = draw.textbbox((0, 0), ln, font=font_body)
                    lw = b[2] - b[0]
                    lh = b[3] - b[1]
                    x = (CANVAS_WIDTH - lw) // 2 - b[0]
                    draw.text((x + 1, y_cursor + 1), ln, font=font_body, fill=(0, 0, 0, 130))
                    draw.text((x, y_cursor), ln, font=font_body, fill=TEXT_COLOR)
                    y_cursor += lh + 8
                y_cursor -= 8

        final_img = canvas.convert("RGB")
        lower = (output_path or "").lower()

        if lower.endswith(".png"):
            final_img.save(output_path, format="PNG", optimize=True, compress_level=4)
        else:
            final_img.save(output_path, format="JPEG", quality=95, optimize=True, subsampling=0)

        log(f"Sosyal medya karti olusturuldu: {output_path}")
        return output_path

    except Exception as e:
        log(f"Kart olusturma hatasi: {e}", "ERROR")
        return image_path


# ── STREAMLIT ARAYÜZÜ ──
st.set_page_config(page_title="Story Asistanım", page_icon="📸", layout="centered")
st.title("📸 Story Asistanım")
st.markdown("Fotoğrafı yükle, metinleri yaz, saniyeler içinde o muhteşem şablonu indir!")

col1, col2 = st.columns(2)
with col1:
    # value="" ile boş başlatıyoruz, placeholder ile arka planda ipucu veriyoruz
    title_text = st.text_input(
        "📝 Başlık (Marka / Model / Konu)", 
        value="", 
        placeholder="Örn: DAYANIKLILIĞIN ADI TOYOTA COROLLA"
    )
with col2:
    body_text = st.text_area(
        "📄 Alt Metin (Fiyat / Detay)", 
        value="", 
        placeholder="Örn: Sadece bu hafta geçerlidir! Fiyat: 1.250.000 TL",
        height=150
    )

uploaded_file = st.file_uploader("⬆️ Araç/Haber Görselini Yükle",
                                 type=['jpg', 'jpeg', 'png'])

if st.button("🎨 Şablonu Oluştur", type="primary", use_container_width=True):
    if uploaded_file is None:
        st.warning("Lütfen bir görsel yükleyin!")
    else:
        with st.spinner("Şablon hazırlanıyor..."):
            temp_dir = tempfile.mkdtemp()
            input_path = os.path.join(temp_dir, "input_img.png")
            output_path = os.path.join(temp_dir, "story_card.png")

            with open(input_path, "wb") as f:
                f.write(uploaded_file.getbuffer())

            full_text = f"{title_text}\n{body_text}"
            result_path = create_social_card(full_text, input_path, output_path)

            if result_path and result_path != input_path and os.path.exists(result_path):
                st.success("Şablon başarıyla oluşturuldu!")
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
            else:
                st.error("Şablon oluşturulamadı. Konsoldaki log'a bak.")
