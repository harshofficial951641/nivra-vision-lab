import SwiftUI

@main
struct NivraApp: App {
    var body: some Scene {
        WindowGroup { HomeView().preferredColorScheme(.dark) }
    }
}

enum NivraRole: String, CaseIterable, Identifiable {
    case camera, guardPhone, wall
    var id: String { rawValue }
    var title: String { switch self { case .camera: "Camera"; case .guardPhone: "Guard"; case .wall: "Camera wall" } }
    var detail: String { switch self { case .camera: "Stream from this phone"; case .guardPhone: "Alerts and live location"; case .wall: "Watch your site's cameras" } }
    var symbol: String { switch self { case .camera: "video.fill"; case .guardPhone: "shield.lefthalf.filled"; case .wall: "rectangle.split.2x2.fill" } }
    var path: String { self == .guardPhone ? "guard" : rawValue }
    var url: URL { URL(string: "https://nivra.tanishq.work/\(path)")! }
}

/// Pairing tokens stay in the fragment and are never sent to unrelated hosts.
func pairingURL(_ text: String) -> URL? {
    guard let url = URL(string: text.trimmingCharacters(in: .whitespacesAndNewlines)),
          let parts = URLComponents(url: url, resolvingAgainstBaseURL: false),
          parts.user == nil, parts.password == nil, parts.port == nil else { return nil }
    let path: String
    if parts.scheme?.lowercased() == "https", parts.host?.lowercased() == "nivra.tanishq.work" {
        path = parts.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
    } else if parts.scheme?.lowercased() == "nivra", let host = parts.host {
        path = host
    } else { return nil }
    let key = ["wall", ""].contains(path) ? "operator" : "pair"
    guard ["camera", "guard", "wall", ""].contains(path),
          let fragment = parts.fragment,
          let token = URLComponents(string: "?\(fragment)")?.queryItems?.first(where: { $0.name == key })?.value,
          token.range(of: "^[A-Za-z0-9_-]{30,100}$", options: .regularExpression) != nil else { return nil }
    return URL(string: "https://nivra.tanishq.work/\(path.isEmpty ? "wall" : path)#\(key)=\(token)")
}
