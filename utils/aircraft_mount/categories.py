"""挂载类别定义（与 Dassault 挂载能力图分类对齐）。"""

RAFALE_MOUNT_CATEGORIES: dict[str, dict[str, str]] = {
    'air_to_air': {'label_en': 'AIR TO AIR', 'label_zh': '空空导弹'},
    'air_to_ground': {'label_en': 'AIR TO GROUND', 'label_zh': '空地导弹'},
    'air_to_sea': {'label_en': 'AIR TO SEA', 'label_zh': '反舰导弹'},
    'bombs_guided': {'label_en': 'BOMBS - GUIDED', 'label_zh': '精确制导炸弹'},
    'bombs_conventional': {'label_en': 'BOMBS - CONVENTIONAL', 'label_zh': '常规炸弹'},
    'electronic_warfare': {'label_en': 'ELECTRONIC WARFARE', 'label_zh': '电子战/干扰设备'},
    'pods_fuel': {'label_en': 'PODS / FUEL', 'label_zh': '吊舱与副油箱'},
    'laser_designation': {'label_en': 'LASER DESIGNATION PODS', 'label_zh': '激光制导/瞄准吊舱'},
    'nuclear': {'label_en': 'NUCLEAR', 'label_zh': '核武器'},
    'fuel': {'label_en': 'FUEL', 'label_zh': '副油箱'},
}
