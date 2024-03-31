import requests
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont


def overlay_text(image, text, position, font_size=80, font_color=(255, 255, 255), font_path=None):
    """
    Overlay text on an image.
    
    Args:
        image (PIL.Image.Image): The image to overlay text on.
        text (str): The text to overlay.
        position (tuple): The position to place the text (x, y).
        font_size (int): The size of the font.
        font_color (tuple): The color of the font in RGB format.
        font_path (str): The path to the font file (optional).
        
    Returns:
        PIL.Image.Image: The image with overlaid text.
    """
    draw = ImageDraw.Draw(image)
    if font_path:
        font = ImageFont.truetype(font_path, font_size)
    else:
        font = ImageFont.load_default()
    draw.text(position, text, font=font, fill=font_color)
    return image

def overlay_image(background_image, face_overlay_image, badge_overlay_image):
     # Paste overlay on blue background
    background_image.paste(face_overlay_image, (30, 180), face_overlay_image)
 
    # Paste overlay on blue background
    background_image.paste(badge_overlay_image, (30, 0), badge_overlay_image)
    
    return background_image

def get_image_from_url(image_url: str) -> Image:
    response = requests.get(image_url)
    image_bytes = BytesIO(response.content)
    image = Image.open(image_bytes, formats=["png"]).resize((180, 180)).convert("RGBA")
    return image

def generate_image(player, type: str, score_dict: dict) -> Image:
    badge_path = f"https://images.fotmob.com/image_resources/logo/teamlogo/{player.team_id}.png"
    player_path = f"https://images.fotmob.com/image_resources/playerimages/{player.id}.png"

    badge = get_image_from_url(badge_path)
    player = get_image_from_url(player_path)

    blue_background = Image.new('RGBA', (640, 360), color=(3, 70, 148))
    with_images = overlay_image(blue_background, player, badge)

    score_list = list(score_dict.values())
    score_string = f"{score_list[0]}-{score_list[1]}"

    if type == "goal":
        text = "GOAL"
        with_text = overlay_text(with_images, text, position=(260, 0),
                                    font_size=200, font_path="font.otf")
    elif type == "assist":
        text = "ASSIST"
        with_text = overlay_text(with_images, text, position=(220, 0),
                                    font_size=200, font_path="font.otf")

    final_image = overlay_text(with_text, score_string, position=(300, 160),
                                    font_size=200, font_path="font.otf")

    return final_image