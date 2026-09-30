"""The four plates. Each is a pure function of a view model, a theme and a variant."""

# (file name suffix, theme mode, mobile layout)
VARIANTS = [
    ("", "dark", False),
    ("-light", "light", False),
    ("-mobile", "dark", True),
    ("-mobile-light", "light", True),
]
