import Foundation

/// 目录数据总包（与 data.json /api/data 一致）
struct CatalogPayload: Codable {
    var version: Int?
    var modes: [String: String]
    var stovl_strategies: [String: String]?
    var tiltrotor_strategies: [String: String]?
    var simulators: [SimulatorEntry]?
    var carriers: [Carrier]
    var aircraft: [Aircraft]
    var missile_interception_presets: MissileInterceptionPresets?
    var takeoff_config: TakeoffConfigPayload?
    var missile_interception_config: MissileInterceptionConfigPayload?
    var combat_radius_presets: [CombatRadiusPresetItem]?
    var combat_radius_config: CombatRadiusConfigPayload?
}

struct TakeoffConfigPayload: Codable {
    var ui: TakeoffUiDefaults?
    var stovl_strategy_descriptions: [String: String]?
    var tiltrotor_strategy_descriptions: [String: String]?
}

struct TakeoffUiDefaults: Codable {
    var default_mode: String?
    var default_strategy: String?
    var default_temp_c: Double?
}

struct MissileInterceptionConfigPayload: Codable {
    var ui: MissileInterceptionUiDefaults?
    var traj_types: [String: String]?
}

struct MissileInterceptionUiDefaults: Codable {
    var nm: Int?
    var ni: Int?
    var vm: Double?
    var rcs: Double?
    var traj: String?
    var awacs_area: Double?
    var awacs_type: String?
    var standoff: Double?
    var ship_area: Double?
    var ship_type: String?
    var sam_range: Double?
    var vi: Double?
    var interceptor_dia: Double?
    var seeker_type: String?
    var tlock: Double?
    var minr: Double?
    var discovery_km: Double?
    var pk: Double?
    var has_awacs: Bool?
}

/// 启动页模拟器条目
struct SimulatorEntry: Codable, Identifiable, Hashable {
    var id: String
    var name: String
    var eyebrow: String?
    var subtitle: String?
    var html: String?
    var miniprogram_page: String?
    var ios_route: String?
}

/// 作战半径配置
struct CombatRadiusConfigPayload: Codable {
    var version: Int?
    var ui: CombatRadiusUiDefaults?
    var planform_labels: [String: String]?
    var layout_labels: [String: String]?
}

struct CombatRadiusUiDefaults: Codable {
    var default_anchor1_id: String?
    var default_anchor2_id: String?
    var default_target_id: String?
    var default_ld1: Double?
    var default_ld2: Double?
}

/// 作战半径机型几何预设
struct CombatRadiusPresetItem: Codable, Identifiable, Hashable {
    var id: String
    var name: String
    var nation: String?
    var AR: Double
    var sweep_deg: Double
    var wing_loading: Double
    var tc: Double
    var mach: Double
    var alt_m: Double
    var planform: String
    var layout: String
    var bwb: Bool
    var rough: Bool
    var ld_known: Double?
    var notes: String?
}

/// 作战半径 / 升阻比估算结果
struct CombatRadiusResult: Codable {
    var success: Bool
    var error: String?
    var Cf0: Double?
    var k_e: Double?
    var kappa_A: Double?
    var anchors: [CombatRadiusRow]?
    var target: CombatRadiusRow?
}

struct CombatRadiusRow: Codable, Identifiable, Hashable {
    var name: String
    var ld: Double
    var CL: Double?
    var e_used: Double?
    var CD0: Double?
    var CDi: Double?
    var CDw: Double?
    var CD: Double?
    var target_ld: Double?
    var error: Double?
    var id: String { name }
}

/// 饱和打击四类预设
struct MissileInterceptionPresets: Codable {
    var asm: [MissileInterceptionPresetItem]?
    var aew: [MissileInterceptionPresetItem]?
    var ship: [MissileInterceptionPresetItem]?
    var sam: [MissileInterceptionPresetItem]?
}

/// 饱和打击单项预设（字段按类型可选）
struct MissileInterceptionPresetItem: Codable, Identifiable, Hashable {
    var id: String
    var name: String
    var nation: String?
    var vm: Double?
    var rcs: Double?
    var traj: String?
    var area: Double?
    var type: String?
    var standoff: Double?
    var vi: Double?
    var dia: Double?
    var guidance: String?
    var range: Double?
    var max_alt: Double?
    var maneuver_class: String?
}

/// 饱和打击仿真结果
struct MissileInterceptionResult: Codable {
    var success: Bool
    var error: String?
    var nm: Int?
    var ni: Int?
    var pk: Double?
    var t_lock_s: Double?
    var n_rounds: Int?
    var expected_leak: Double?
    var intercept_rate: Double?
    var final_trials: Int?
    var note: String?
    var windows: [MissileInterceptionWindow]?
    var best: MissileInterceptionPlan?
    var avg_survivors: [Double]?
    var all_candidates: [MissileInterceptionCandidate]?
    var engage_dist: Double?
    var binding: String?
    var speed_factor: Double?
    var ship_radar_factor: Double?
    var seeker_factor: Double?
    var rcs_factor: Double?
    var traj_factor: Double?
    var maneuver_factor: Double?
    var maneuver_class: String?
    var dive_entry_km: Double?
    var dive_angle_deg: Double?
    var sam_max_alt_km: Double?
    var h_engage_m: Double?
    var awacs_power: Double?
    var awacs_horizon: Double?
    var awacs_total: Double?
    var awacs_detect_km: Double?
    var ship_lock: Double?
    var ship_search: Double?
    var ship_detect_km: Double?
    var detect_max_km: Double?
    var sam_range: Double?
    var standoff: Double?
    var has_awacs: Bool?
    var h_target_m: Double?
}

struct MissileInterceptionWindow: Codable, Identifiable, Hashable {
    var round: Int
    var dist_start_km: Double
    var t_fly_s: Double
    var total_t_s: Double
    var dist_end_km: Double
    var id: Int { round }
}

struct MissileInterceptionPlan: Codable, Hashable {
    var name: String
    var plan: [Int]
}

struct MissileInterceptionCandidate: Codable, Identifiable, Hashable {
    var name: String
    var plan: [Int]
    var expected_leak: Double
    var id: String { "\(name)-\(plan.map(String.init).joined(separator: ","))" }
}

/// 航母记录
struct Carrier: Codable, Identifiable, Hashable {
    var id: String
    var name: String
    var nation: String
    var max_speed_kt: Double?
    var total_deck_length_m: Double
    var ski_jump: Bool
    var ski_jump_angle_deg: Double?
    var ski_jump_height_m: Double?
    var f35b_capable: Bool
    var notes: String?
    var deck_length_source: String?

    var displayName: String { "\(name)（\(nation)）" }
}

/// 战斗机记录
struct Aircraft: Codable, Identifiable, Hashable {
    var id: String
    var name: String
    var type_label: String
    var mtow_kg: Double
    var empty_kg: Double
    var internal_fuel_kg: Double
    var max_payload_kg: Double
    var bvr_missile: String
    var missile_mass_kg: Double
    var wingspan_m: Double
    var wing_area_m2: Double
    var sweep_le_deg: Double
    var cd0: Double
    var t_max_sl_n: Double?
    var t_main_stovl_sl_n: Double?
    var t_liftfan_sl_n: Double?
    var t_rollposts_sl_n: Double?
    var shaft_power_sl_w: Double?
    var prop_diameter_m: Double?
    var nacelle_blockage_frac: Double?
    var notes: String?
    var wing_height_m: Double?
    var exhaust_d0_m: Double?
    var exhaust_height_m: Double?
    var exhaust_mdot_kg_s: Double?
}

/// 规格行
struct SpecItem: Identifiable, Hashable {
    var id: String { label }
    var label: String
    var value: String
}

/// 模式/策略按钮项
struct ModeItem: Identifiable, Hashable {
    var id: String
    var label: String
}

/// 仿真 API 返回（字段按需解码）
struct SimulationResult: Codable {
    var success: Bool
    var error: String?
    var output: String?
    var deck_launch_ok: Bool?
    var deck_margin_m: Double?
    var distance_m: Double?
    var output_summary: String?
    var trajectory: [TrajectoryPoint]?
    var deck_profile: DeckProfile?
}

struct TrajectoryPoint: Codable, Hashable {
    var x: Double
    var y: Double
    var phase: String?
}

struct DeckProfile: Codable, Hashable {
    var points: [[Double]]
    var total_deck_length_m: Double?
    var takeoff_distance_m: Double?
    var lip_height_m: Double?
}

/// 状态条样式
enum StatusKind {
    case idle
    case loading
    case ok
    case error
}

extension Encodable {
    /// 将 Codable 转为 JSON 字典，供本地仿真 payload 拼装
    func asJSONDictionary() throws -> [String: Any] {
        let data = try JSONEncoder().encode(self)
        let obj = try JSONSerialization.jsonObject(with: data)
        guard let dict = obj as? [String: Any] else {
            throw NSError(
                domain: "CarrierTakeOff",
                code: 2,
                userInfo: [NSLocalizedDescriptionKey: "无法编码为 JSON 对象"]
            )
        }
        return dict
    }
}
