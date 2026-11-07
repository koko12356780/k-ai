"""Named palettes; the app's common layout stays consistent across themes."""

NAMES = ("Night", "Daylight", "Ocean", "Mint", "Rose")

BASE = ("#10131c", "#e9edf6", "#151a26", "#eeeaff", "#9da9bf", "#b9acff",
        "#232b3e", "#34405a", "#303c55", "#68748b", "#1b2231", "#8c73f8",
        "#0b0b18", "#a18aff", "#6251a9", "#2b304b", "#d8cdff", "#1a2130",
        "#2a344a", "#252d40", "#141a25", "#36415b")

PALETTES = {
    "Daylight": ("#f5f6fb", "#192238", "#e9edf6", "#34246b", "#58657c", "#6042ae",
                 "#e1e6f1", "#bcc6da", "#d0d8e9", "#778399", "#ffffff", "#7351d8",
                 "#ffffff", "#8464e2", "#c8b9f6", "#ddd4f7", "#382569", "#ffffff",
                 "#d1d9e8", "#d1d9e8", "#edf0f7", "#bac5da"),
    "Ocean": ("#081b29", "#e0f3ff", "#0b2537", "#dcf7ff", "#93b6ca", "#67d7eb",
              "#15364b", "#28566f", "#204a63", "#67879a", "#102d40", "#5ccce5",
              "#06202c", "#85e2f1", "#27627b", "#16445e", "#c0f6ff", "#102d40",
              "#20485f", "#20485f", "#0a2231", "#32627a"),
    "Mint": ("#0c1d18", "#e7f4ec", "#12281f", "#e0ffe9", "#9cbaaa", "#91dfb1",
             "#203d30", "#385f4a", "#2c503c", "#718f7e", "#193227", "#8bd7a8",
             "#0b2718", "#b0edc7", "#467b59", "#254d37", "#d5f9e0", "#193227",
             "#2c4c3a", "#2c4c3a", "#10271b", "#426850"),
    "Rose": ("#21151d", "#faeaf1", "#2d1b27", "#ffe7f3", "#c0a2b4", "#f3accc",
             "#422a39", "#694458", "#56384a", "#9b7b8e", "#35212e", "#f0a1c5",
             "#341023", "#ffc5df", "#8c5071", "#593349", "#ffe0f1", "#35212e",
             "#573549", "#573549", "#2a1823", "#765067"),
}


def stylesheet(base, name):
    import re
    palette = PALETTES.get(name, BASE)
    mapping = dict(zip(BASE, palette))
    return re.sub(r"#[0-9a-fA-F]{6}", lambda m: mapping.get(m[0], m[0]), base)
