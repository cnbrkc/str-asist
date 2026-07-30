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
CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1920

BG_COLOR_RGBA = (18, 25, 36, 255)
TEXT_COLOR = (255, 255, 255, 255)

# Yazı dış çizgi (stroke) — ince ama belirgin
TITLE_STROKE_COLOR = (0, 0, 0, 230)
BODY_STROKE_COLOR = (0, 0, 0, 210)

# Dış çizgi kalınlıkları (px) — inceltildi
TITLE_STROKE_WIDTH = 2
BODY_STROKE_WIDTH = 2

# Overlay alpha — eski halin bir tık altında (daha şeffaf)
OVERLAY_ALPHA = 100

FONT_BOLD_PATH = os.path.join(get_project_root(), "assets", "Roboto-Bold.ttf")
FONT_REG_PATH = os.path.join(get_project_root(), "assets", "Roboto-Regular.ttf")


def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = FONT_BOLD_PATH if bold else FONT_REG_PATH
    if not os.path.exists(path):
        log(f"Font bulunamadi: {path}. Varsayilan kullaniliyor.", "WARNING")
        return ImageFont.load_default()
    return ImageFont.truetype(path, size)


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int, stroke_width: int = 0) -> list:
    """Metni max_width'e göre satırlara böler. stroke_width dahil edilerek daha doğru ölçer."""
    words = text.split()
    lines = []
    current_line = ""

    for word in words:
        test_line = f"{current_line} {word}".strip()
        bbox = draw.textbbox((0, 0), test_line, font=font, stroke_width=stroke_width, anchor="lt")

        if (bbox[2] - bbox[0]) <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
                current_line = ""

            bbox_word = draw.textbbox((0, 0), word, font=font, stroke_width=stroke_width, anchor="lt")
            if (bbox_word[2] - bbox_word[0]) > max_width:
                # Tek kelime bile sığmıyorsa karakter karakter böl
                temp_line = ""
                for char in word:
                    test_char = temp_line + char
                    bbox_c = draw.textbbox((0, 0), test_char, font=font, stroke_width=stroke_width, anchor="lt")
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
    """
    Başlıkta noktalama işaretleri ve özel karakterler KORUNUR.
    Sadece fazla boşluklar kırpılır; büyük harf sadece görsel tutarlılık için.
    """
    lines = [ln.strip() for ln in (post_text or "").split("\n") if ln.strip()]
    title = lines[0] if lines else ""
    if title:
        title = re.sub(r"\s+", " ", title).strip().upper()
    body = "\n".join(lines[1:]) if len(lines) > 1 else ""
    return title, body


def _draw_centered_line(canvas, x_center: int, y_top: int, text: str, font,
                         fill, stroke_width: int, stroke_fill) -> int:
    """
    Tek satır yazıyı stroke + fill ile çizer.
    anchor="mt" ile yatayda tam ortalanmış, dikeyde üst hizalı → satırlar arası oynama yok.

    Dönüş: satırın pixel yüksekliği (lh).
    """
    draw = ImageDraw.Draw(canvas)
    b = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width, anchor="lt")
    lh = b[3] - b[1]

    draw.text(
        (x_center, y_top),
        text,
        font=font,
        fill=fill,
        stroke_width=stroke_width,
        stroke_fill=stroke_fill,
        anchor="mt",
    )
    return lh


def create_social_card(post_text: str, image_path: str, output_path: str) -> str:
    """
    Story kart üretimi — Profesyonel haber edası:
    • Başlıkta noktalama serbest
    • Harflerde ince siyah dış çizgi + arkada yumuşak blur gölge
    • anchor="mt" ile düzgün ortalama (satır oynaması yok)
    • Şeffaf arka plan (overlay 100 alpha) — görsel ön planda
    • Tüm elementler (logo, başlık, foto, alt metin) her zaman dikey ortada
    """
    try:
        title, body = _prepare_text(post_text)

        side_padding = 60
        max_text_width = CANVAS_WIDTH - side_padding * 2
        logo_size = 210            # logo boyutu
        logo_top_margin = 80      # logo ile canvas üst kenarı arasındaki sabit boşluk

        # Gap'ler dinamik — paket sığmıyorsa önce gap'leri daraltırız, fontu değil.
        gap_max = 70              # elementler arası (logo↔başlık, başlık↔foto, foto↔altmetin) maksimum boşluk
        gap_min = 28              # bu değerin altına gap'i düşürmeyiz; düşerse gap'i sabit tutup font küçültürüz
        gap_step = 4              # her daraltma adımında gap'i ne kadar küçültürüz

        line_gap_max = 12         # başlık satırları arası maksimum
        line_gap_min = 6          # satır arası minimum
        body_line_gap_max = 10
        body_line_gap_min = 5

        max_img_h = 880
        img_max_w = CANVAS_WIDTH - 120  # kenarlardan 60'ar px boşluk (köşelere dayanmaz)

        logo_path = os.path.join(get_project_root(), "assets", "logo.png")
        has_logo = os.path.exists(logo_path)

        dummy_img = Image.new("RGB", (1, 1))
        dummy_draw = ImageDraw.Draw(dummy_img)

        # Font küçültme limitleri
        TITLE_FONT_MIN = 48       # başlık fontu bu alt sınırın altına inmez
        BODY_FONT_MIN = 32        # alt metin fontu bu alt sınırın altına inmez

        title_font_size = 72
        body_font_size = 60

        def _compute_layout(tfs, bfs, g, tlg, blg):
            """Belirli font + gap değerleri için paket yüksekliğini hesaplar."""
            ft = _get_font(tfs, bold=True)
            fb = _get_font(bfs, bold=False)

            tl = _wrap_text(dummy_draw, title, ft, max_text_width, stroke_width=TITLE_STROKE_WIDTH) if title else []
            bl = _wrap_text(dummy_draw, body, fb, max_text_width, stroke_width=BODY_STROKE_WIDTH) if body else []

            th = 0
            for ln in tl:
                b = dummy_draw.textbbox((0, 0), ln, font=ft, stroke_width=TITLE_STROKE_WIDTH, anchor="lt")
                th += (b[3] - b[1]) + tlg
            if tl:
                th -= tlg

            bh = 0
            for ln in bl:
                b = dummy_draw.textbbox((0, 0), ln, font=fb, stroke_width=BODY_STROKE_WIDTH, anchor="lt")
                bh += (b[3] - b[1]) + blg
            if bl:
                bh -= blg

            dyn_img_h = min(max_img_h, max(100, CANVAS_HEIGHT - 80))

            elems = []
            if tl:
                elems.append(("title", th))
            elems.append(("image", dyn_img_h))
            if bl:
                elems.append(("body", bh))

            ptotal = sum(h for _, h in elems) + g * (len(elems) - 1)

            # Logo dahil değil ama logoya yer ayrılması gerekir (üst kenardan)
            logo_reserve = (logo_size + g) if has_logo else 0  # logo_packet_gap = g ile aynı
            max_for_logo = CANVAS_HEIGHT - 2 * (logo_top_margin + logo_reserve) if has_logo else CANVAS_HEIGHT - 80
            eff_max = min(max_for_logo, CANVAS_HEIGHT - 80)

            return tl, bl, ft, fb, th, bh, dyn_img_h, ptotal, eff_max

        # ── Aşama 1: gap'leri daraltarak sığdır (font sabit) ──
        gap = gap_max
        title_line_gap = line_gap_max
        body_line_gap = body_line_gap_max

        while True:
            (title_lines, body_lines, font_title, font_body,
             title_h, body_h, dynamic_max_img_h,
             packet_total_h, effective_max) = _compute_layout(
                title_font_size, body_font_size, gap, title_line_gap, body_line_gap
            )

            if packet_total_h <= effective_max:
                break  # sığdı!

            # Önce element gap'ini daralt
            if gap > gap_min:
                gap = max(gap_min, gap - gap_step)
                continue
            # Sonra başlık satır arası
            if title_line_gap > line_gap_min:
                title_line_gap = max(line_gap_min, title_line_gap - 2)
                continue
            # Sonra alt metin satır arası
            if body_line_gap > body_line_gap_min:
                body_line_gap = max(body_line_gap_min, body_line_gap - 1)
                continue

            # Gap'ler minimumda ama hâlâ sığmıyor → font küçültme aşamasına geç
            break

        # ── Aşama 2: gap'ler minimumda, hâlâ sığmıyorsa fontu küçült ──
        while packet_total_h > effective_max:
            reduced = False
            if title_font_size > TITLE_FONT_MIN:
                title_font_size -= 2
                reduced = True
            if body_font_size > BODY_FONT_MIN:
                body_font_size -= 2
                reduced = True
            if not reduced:
                break  # ikisi de minimumda, daha fazla küçültülemiyor

            (title_lines, body_lines, font_title, font_body,
             title_h, body_h, dynamic_max_img_h,
             packet_total_h, effective_max) = _compute_layout(
                title_font_size, body_font_size, gap, title_line_gap, body_line_gap
            )

        # ── Ana görseli işle ──
        main_img = None
        img_actual_h = 0
        if image_path and os.path.exists(image_path):
            try:
                src = Image.open(image_path).convert("RGB")
                main_img = _fit_contain(src, img_max_w, dynamic_max_img_h)
                img_actual_h = main_img.height
            except Exception as e:
                log(f"Ana gorsel islenemedi: {e}", "WARNING")

        # ── Yerleşim planı ──
        # PAKET = (başlık + foto + alt metin) → canvas'ın TAM ortasında
        # LOGO = başlığın tam `gap` kadar üstünde, sağdan soldan ortalı
        packet_elements = []
        if title_lines:
            packet_elements.append(("title", title_h))
        if main_img is not None:
            packet_elements.append(("image", img_actual_h))
        if body_lines:
            packet_elements.append(("body", body_h))

        num_gaps = max(0, len(packet_elements) - 1)
        packet_total_h = sum(h for _, h in packet_elements) + gap * num_gaps

        # Paket CANVAS'IN TAM ORTASINDA (logo hariç hesaplanır)
        packet_y_start = (CANVAS_HEIGHT - packet_total_h) // 2

        # Logo: başlığın tam `gap` kadar üstünde (logo_packet_gap = gap ile aynı tutulur)
        if has_logo:
            logo_y = packet_y_start - gap - logo_size

        # ── Tuvali oluştur ──
        canvas = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), BG_COLOR_RGBA)

        # Hafif blur'lu arka plan görseli
        if image_path and os.path.exists(image_path):
            try:
                src = Image.open(image_path).convert("RGB")
                bg = _fit_cover(src, CANVAS_WIDTH, CANVAS_HEIGHT)
                bg = bg.filter(ImageFilter.GaussianBlur(30))
                canvas.paste(bg, (0, 0))
            except Exception as e:
                log(f"Blur arka plan hazirlanamadi: {e}", "WARNING")

        # Karartma overlay — 100 alpha (çok şeffaf)
        overlay = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), (18, 25, 36, OVERLAY_ALPHA))
        canvas = Image.alpha_composite(canvas, overlay)

        draw = ImageDraw.Draw(canvas)

        # ── Logo'yu çiz (paketin üstünde, sabit konumda) ──
        if has_logo:
            try:
                logo = Image.open(logo_path).convert("RGBA")
                logo = logo.resize((logo_size, logo_size), Image.LANCZOS)
                logo_x = (CANVAS_WIDTH - logo_size) // 2
                canvas.paste(logo, (logo_x, logo_y), logo)
            except Exception as e:
                log(f"Logo islenemedi: {e}", "WARNING")

        # ── Paket elementlerini sırayla çiz (paket ortada) ──
        y_cursor = packet_y_start
        for idx, (elem_type, _) in enumerate(packet_elements):
            if idx > 0:
                y_cursor += gap

            if elem_type == "title":
                for ln in title_lines:
                    lh = _draw_centered_line(
                        canvas,
                        x_center=CANVAS_WIDTH // 2,
                        y_top=y_cursor,
                        text=ln,
                        font=font_title,
                        fill=TEXT_COLOR,
                        stroke_width=TITLE_STROKE_WIDTH,
                        stroke_fill=TITLE_STROKE_COLOR,
                    )
                    y_cursor += lh + title_line_gap
                y_cursor -= title_line_gap

            elif elem_type == "image":
                img_w, img_h = main_img.size
                img_x = (CANVAS_WIDTH - img_w) // 2

                # Yuvarlatılmış köşe maskesi
                mask = Image.new("L", (img_w, img_h), 0)
                mdraw = ImageDraw.Draw(mask)
                mdraw.rounded_rectangle((0, 0, img_w, img_h), radius=22, fill=255)

                # Çok katmanlı, blur'lu derin gölge — görsel havada dursun
                shadow_pad = 30
                shadow = Image.new("RGBA", (img_w + shadow_pad * 2, img_h + shadow_pad * 2), (0, 0, 0, 0))
                sdraw = ImageDraw.Draw(shadow)
                for i in range(8):
                    alpha = max(0, 60 - i * 6)
                    off = 8 + i * 2
                    sdraw.rounded_rectangle(
                        (off, off, img_w + off, img_h + off),
                        radius=26,
                        fill=(0, 0, 0, alpha),
                    )
                shadow = shadow.filter(ImageFilter.GaussianBlur(8))
                canvas.alpha_composite(shadow, dest=(img_x - shadow_pad, y_cursor - 6))

                main_rgba = main_img.convert("RGBA")
                canvas.paste(main_rgba, (img_x, y_cursor), mask)

                # İnce beyaz çerçeve — görseli hafifçe çerçevele
                border_draw = ImageDraw.Draw(canvas)
                border_draw.rounded_rectangle(
                    (img_x, y_cursor, img_x + img_w, y_cursor + img_h),
                    radius=22,
                    outline=(255, 255, 255, 70),
                    width=2,
                )

                y_cursor += img_h

            elif elem_type == "body":
                for ln in body_lines:
                    lh = _draw_centered_line(
                        canvas,
                        x_center=CANVAS_WIDTH // 2,
                        y_top=y_cursor,
                        text=ln,
                        font=font_body,
                        fill=TEXT_COLOR,
                        stroke_width=BODY_STROKE_WIDTH,
                        stroke_fill=BODY_STROKE_COLOR,
                    )
                    y_cursor += lh + body_line_gap
                y_cursor -= body_line_gap

        # ── Kaydet ──
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
    title_text = st.text_input(
        "📝 Başlık (Marka / Model / Konu)",
        value="",
        placeholder="Örn: DAYANIKLILIĞIN ADI: TOYOTA COROLLA!"
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
