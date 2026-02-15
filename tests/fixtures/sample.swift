import Foundation

class NetworkManager {
    let baseURL: String
    var headers: [String: String] = [:]

    init(baseURL: String) {
        self.baseURL = baseURL
    }

    func fetch(endpoint: String) async throws -> Data {
        let url = URL(string: "\(baseURL)/\(endpoint)")!
        let (data, _) = try await URLSession.shared.data(from: url)
        return data
    }
}

struct UserProfile {
    let id: String
    let name: String
    let email: String
}

protocol Cacheable {
    var cacheKey: String { get }
    func invalidate()
}

enum AppError: Error {
    case networkError(String)
    case parseError
    case unauthorized
}

func formatDate(_ date: Date) -> String {
    let formatter = DateFormatter()
    formatter.dateStyle = .medium
    return formatter.string(from: date)
}
