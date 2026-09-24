"""Generate deterministic PNG assets for the built-in mock screen graph."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "fixtures" / "reservation-flow"
WIDTH = 1280
HEIGHT = 720
PHONE_LEFT = 360
PHONE_RIGHT = 920
PHONE_TOP = 50
PHONE_BOTTOM = 670


def base_screen(title: str, subtitle: str) -> np.ndarray:
    frame = np.full((HEIGHT, WIDTH, 3), (20, 27, 38), dtype=np.uint8)
    cv2.rectangle(
        frame,
        (PHONE_LEFT, PHONE_TOP),
        (PHONE_RIGHT, PHONE_BOTTOM),
        (239, 242, 246),
        -1,
    )
    cv2.rectangle(
        frame,
        (PHONE_LEFT, PHONE_TOP),
        (PHONE_RIGHT, PHONE_BOTTOM),
        (78, 91, 109),
        4,
    )
    cv2.putText(
        frame,
        title,
        (PHONE_LEFT + 55, PHONE_TOP + 90),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.35,
        (34, 42, 55),
        3,
        cv2.LINE_AA,
    )
    cv2.putText(
        frame,
        subtitle,
        (PHONE_LEFT + 55, PHONE_TOP + 140),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (91, 103, 119),
        2,
        cv2.LINE_AA,
    )
    return frame


def draw_button(
    frame: np.ndarray,
    label: str,
    *,
    left: int = 460,
    top: int = 500,
    width: int = 360,
    height: int = 80,
    color: tuple[int, int, int] = (65, 174, 103),
) -> None:
    cv2.rectangle(frame, (left, top), (left + width, top + height), color, -1)
    text_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.85, 2)
    text_x = left + (width - text_size[0]) // 2
    text_y = top + (height + text_size[1]) // 2
    cv2.putText(
        frame,
        label,
        (text_x, text_y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.85,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )


def generate() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)

    home = base_screen("TapBot Demo", "Hardware-free mock application")
    cv2.putText(
        home,
        "Welcome back",
        (460, 300),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (53, 63, 77),
        2,
        cv2.LINE_AA,
    )
    draw_button(home, "Open reservation")

    reservation = base_screen("Reservation", "Review your booking details")
    cv2.putText(
        reservation,
        "Table for 2",
        (460, 285),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.95,
        (53, 63, 77),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        reservation,
        "Today  19:30",
        (460, 340),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (91, 103, 119),
        2,
        cv2.LINE_AA,
    )
    draw_button(reservation, "Verify photo")
    draw_button(
        reservation,
        "Back",
        left=460,
        top=600,
        width=160,
        height=45,
        color=(116, 123, 132),
    )

    verify_photo = base_screen("Verify Photo", "Take a photo to continue")
    cv2.rectangle(verify_photo, (550, 225), (730, 365), (78, 91, 109), 6)
    cv2.circle(verify_photo, (640, 295), 42, (65, 174, 103), 5)
    cv2.rectangle(verify_photo, (600, 205), (680, 230), (78, 91, 109), -1)
    draw_button(verify_photo, "Return home")

    for name, frame in {
        "home.png": home,
        "reservation.png": reservation,
        "verify-photo.png": verify_photo,
    }.items():
        destination = OUTPUT / name
        if not cv2.imwrite(str(destination), frame):
            raise RuntimeError(f"Could not write {destination}")


if __name__ == "__main__":
    generate()
