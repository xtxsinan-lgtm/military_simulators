import Foundation
import WebKit

/// 设备本地仿真引擎：隐藏 WKWebView + Pyodide，运行与 Web 相同的 Python。
@MainActor
final class LocalSimulatorEngine: NSObject, WKScriptMessageHandler {
    static let shared = LocalSimulatorEngine()

    private var webView: WKWebView?
    private var readyContinuations: [CheckedContinuation<Void, Error>] = []
    private var isReady = false
    private var lastError: String?
    private var preparing = false

    private override init() {
        super.init()
    }

    /// 预加载 Pyodide（首次可能需从 CDN 拉取 wasm；仿真计算始终在本机）
    func prepare() async throws {
        if isReady { return }
        // 允许失败后重试（例如修复 Bundle / 网络后）
        if lastError != nil, !preparing {
            lastError = nil
            webView = nil
        }
        if let lastError {
            throw NSError(
                domain: "LocalSimulatorEngine",
                code: 1,
                userInfo: [NSLocalizedDescriptionKey: lastError]
            )
        }
        try await withCheckedThrowingContinuation { (cont: CheckedContinuation<Void, Error>) in
            readyContinuations.append(cont)
            if !preparing {
                preparing = true
                bootstrapWebView()
            }
        }
    }

    /// 在本地 Pyodide 中运行起飞仿真
    func run(payload: [String: Any]) async throws -> SimulationResult {
        try await prepare()
        guard let webView else {
            throw NSError(
                domain: "LocalSimulatorEngine",
                code: 2,
                userInfo: [NSLocalizedDescriptionKey: "仿真引擎 WebView 未初始化"]
            )
        }
        let result = try await webView.callAsyncJavaScript(
            "return await window.__carrierSim.run(payload);",
            arguments: ["payload": payload],
            contentWorld: .page
        )
        guard let obj = result else {
            throw NSError(
                domain: "LocalSimulatorEngine",
                code: 4,
                userInfo: [NSLocalizedDescriptionKey: "仿真无返回"]
            )
        }
        let data = try JSONSerialization.data(withJSONObject: obj)
        return try JSONDecoder().decode(SimulationResult.self, from: data)
    }

    /// 在本地 Pyodide 中运行饱和打击仿真 / 估算
    func runMissileInterception(payload: [String: Any]) async throws -> MissileInterceptionResult {
        try await prepare()
        guard let webView else {
            throw NSError(
                domain: "LocalSimulatorEngine",
                code: 2,
                userInfo: [NSLocalizedDescriptionKey: "仿真引擎 WebView 未初始化"]
            )
        }
        let result = try await webView.callAsyncJavaScript(
            "return await window.__missileInterceptionSim.run(payload);",
            arguments: ["payload": payload],
            contentWorld: .page
        )
        guard let obj = result else {
            throw NSError(
                domain: "LocalSimulatorEngine",
                code: 4,
                userInfo: [NSLocalizedDescriptionKey: "饱和打击仿真无返回"]
            )
        }
        let data = try JSONSerialization.data(withJSONObject: obj)
        return try JSONDecoder().decode(MissileInterceptionResult.self, from: data)
    }

    /// 在本地 Pyodide 中运行作战半径 / 升阻比估算
    func runCombatRadius(payload: [String: Any]) async throws -> CombatRadiusResult {
        try await prepare()
        guard let webView else {
            throw NSError(
                domain: "LocalSimulatorEngine",
                code: 2,
                userInfo: [NSLocalizedDescriptionKey: "仿真引擎 WebView 未初始化"]
            )
        }
        let result = try await webView.callAsyncJavaScript(
            "return await window.__combatRadiusSim.run(payload);",
            arguments: ["payload": payload],
            contentWorld: .page
        )
        guard let obj = result else {
            throw NSError(
                domain: "LocalSimulatorEngine",
                code: 4,
                userInfo: [NSLocalizedDescriptionKey: "作战半径估算无返回"]
            )
        }
        let data = try JSONSerialization.data(withJSONObject: obj)
        return try JSONDecoder().decode(CombatRadiusResult.self, from: data)
    }

    nonisolated func userContentController(
        _ userContentController: WKUserContentController,
        didReceive message: WKScriptMessage
    ) {
        Task { @MainActor in
            handleBridgeMessage(message.body)
        }
    }

    private func handleBridgeMessage(_ body: Any) {
        guard let dict = body as? [String: Any], let type = dict["type"] as? String else { return }
        switch type {
        case "ready":
            isReady = true
            preparing = false
            lastError = nil
            let conts = readyContinuations
            readyContinuations.removeAll()
            conts.forEach { $0.resume() }
        case "error":
            let text = (dict["text"] as? String) ?? "引擎加载失败"
            lastError = text
            preparing = false
            let conts = readyContinuations
            readyContinuations.removeAll()
            conts.forEach {
                $0.resume(
                    throwing: NSError(
                        domain: "LocalSimulatorEngine",
                        code: 5,
                        userInfo: [NSLocalizedDescriptionKey: text]
                    )
                )
            }
        default:
            break
        }
    }

    private func bootstrapWebView() {
        guard let dataURL = Bundle.main.url(forResource: "data", withExtension: "json"),
              let catalogJSON = try? String(contentsOf: dataURL, encoding: .utf8),
              !catalogJSON.isEmpty
        else {
            failBootstrap("缺少 data.json，请在仓库根目录运行 python3 scripts/build_all.py 后重新编译")
            return
        }

        let config = WKWebViewConfiguration()
        config.userContentController.add(self, name: "simBridge")
        // 由 Swift 注入目录 JSON，避免 WKWebView 在 file:// 下 fetch 失败（status 0）
        let inject = "window.__BUNDLED_CATALOG__ = \(catalogJSON);"
        config.userContentController.addUserScript(
            WKUserScript(source: inject, injectionTime: .atDocumentStart, forMainFrameOnly: true)
        )
        config.preferences.setValue(true, forKey: "allowFileAccessFromFileURLs")
        config.setValue(true, forKey: "allowUniversalAccessFromFileURLs")

        let wv = WKWebView(frame: .zero, configuration: config)
        webView = wv

        guard let htmlURL = Bundle.main.url(forResource: "engine", withExtension: "html") else {
            failBootstrap("缺少 engine.html，请确认已加入 App Bundle（运行 build_all.py）")
            return
        }
        let resourceDir = htmlURL.deletingLastPathComponent()
        wv.loadFileURL(htmlURL, allowingReadAccessTo: resourceDir)
    }

    private func failBootstrap(_ message: String) {
        lastError = message
        preparing = false
        let conts = readyContinuations
        readyContinuations.removeAll()
        conts.forEach {
            $0.resume(
                throwing: NSError(
                    domain: "LocalSimulatorEngine",
                    code: 6,
                    userInfo: [NSLocalizedDescriptionKey: message]
                )
            )
        }
    }
}
