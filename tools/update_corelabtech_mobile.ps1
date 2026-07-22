$ErrorActionPreference = "Stop"

$Root = "D:\corelabtech_mobile"

if (-not (Test-Path -LiteralPath $Root)) {
    throw "Mobile project not found: $Root"
}

$androidMain = @'
package com.corelabtech.mobile

import android.os.Bundle
import android.os.Handler
import android.os.Looper
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import org.json.JSONObject
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.util.UUID

private val AppBackground = Color(0xFF0B0F1A)
private val Panel = Color(0xFF020617)
private val PanelSoft = Color(0xFF07111F)
private val Accent = Color(0xFF00FFCC)
private val TextPrimary = Color(0xFFF8FAFC)
private val TextMuted = Color(0xFFB6C5D6)

data class PhysiologySession(
    val id: String,
    val athleteName: String,
    val sessionType: String,
    val status: String,
    val matchRate: Float,
    val recoveryScore: Int = 0
)

data class PhaseMetric(
    val phase: String,
    val heartRate: String,
    val hrv: String,
    val spo2: String
)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = AppBackground
                ) {
                    CoreLabTechConsumerApp()
                }
            }
        }
    }
}

@Composable
fun CoreLabTechConsumerApp() {
    var displayName by remember { mutableStateOf("Alex") }
    var sessionType by remember { mutableStateOf("Recovery Check") }
    var email by remember { mutableStateOf("client@example.com") }
    var password by remember { mutableStateOf("CoreLabTech123") }
    var authStatus by remember { mutableStateOf("Sign in to sync sessions") }
    var accessToken by remember { mutableStateOf<String?>(null) }
    val sessions = remember {
        mutableStateListOf(
            PhysiologySession("android-demo-001", "Alex", "HBOT Recovery", "ready", 0.94f, 86),
            PhysiologySession("android-demo-002", "Alex", "Post Training", "watch load", 0.81f, 72)
        )
    }
    val metrics = remember {
        listOf(
            PhaseMetric("Before", "64 bpm", "72 ms", "98%"),
            PhaseMetric("During", "88 bpm", "51 ms", "96%"),
            PhaseMetric("After", "69 bpm", "68 ms", "98%")
        )
    }

    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .background(AppBackground)
            .padding(18.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        item {
            HeroCard()
        }

        item {
            ReadinessCard(score = 86, status = "Ready for light recovery work")
        }

        item {
            ConsumerLoginCard(
                email = email,
                password = password,
                status = authStatus,
                tokenReady = accessToken != null,
                onEmailChange = { email = it },
                onPasswordChange = { password = it },
                onRegister = {
                    authStatus = "Creating account..."
                    mobileAuthRequest("/api/auth/register", email, password, displayName) { token, message ->
                        accessToken = token
                        authStatus = message
                    }
                },
                onLogin = {
                    authStatus = "Signing in..."
                    mobileAuthRequest("/api/auth/login", email, password, displayName) { token, message ->
                        accessToken = token
                        authStatus = message
                    }
                }
            )
        }

        item {
            CreateSessionCard(
                displayName = displayName,
                sessionType = sessionType,
                onNameChange = { displayName = it },
                onTypeChange = { sessionType = it },
                onCreate = {
                    sessions.add(
                        0,
                        PhysiologySession(
                            UUID.randomUUID().toString(),
                            displayName,
                            sessionType,
                            "local draft",
                            0.90f,
                            82
                        )
                    )
                }
            )
        }

        item {
            DevicePlanCard()
        }

        item {
            PhaseCard(metrics)
        }

        item {
            Text(
                "Recent recovery sessions",
                color = TextPrimary,
                fontWeight = FontWeight.Bold,
                style = MaterialTheme.typography.titleLarge
            )
        }

        items(sessions) { session ->
            SessionCard(session)
        }

        item {
            ResearchDisclaimer()
        }
    }
}

@Composable
fun HeroCard() {
    AppCard {
        Text("CoreLabTech Recovery", color = Accent, fontWeight = FontWeight.Bold)
        Text(
            "Personal recovery tracker",
            color = TextPrimary,
            fontWeight = FontWeight.Bold,
            style = MaterialTheme.typography.headlineMedium
        )
        Text(
            "Connect wearable FIT data, pulse oximeter readings and session notes to understand how your body responds before, during and after recovery.",
            color = TextMuted
        )
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Button(onClick = {}) { Text("Start Session") }
            OutlinedButton(onClick = {}) { Text("Import FIT/CSV") }
        }
    }
}

@Composable
fun ReadinessCard(score: Int, status: String) {
    AppCard {
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Column {
                Text("Today readiness", color = TextMuted)
                Text("$score", color = TextPrimary, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.displaySmall)
            }
            StatusPill(status)
        }
        LinearProgressIndicator(progress = { score / 100f }, modifier = Modifier.fillMaxWidth())
        Text("Based on HR, HRV, SpO2 and data quality. Not a medical diagnosis.", color = TextMuted)
    }
}

@Composable
fun ConsumerLoginCard(
    email: String,
    password: String,
    status: String,
    tokenReady: Boolean,
    onEmailChange: (String) -> Unit,
    onPasswordChange: (String) -> Unit,
    onRegister: () -> Unit,
    onLogin: () -> Unit
) {
    AppCard {
        Text("Account sync", color = TextPrimary, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
        OutlinedTextField(value = email, onValueChange = onEmailChange, label = { Text("Email") }, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(value = password, onValueChange = onPasswordChange, label = { Text("Password") }, modifier = Modifier.fillMaxWidth())
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = onLogin) { Text("Login") }
            OutlinedButton(onClick = onRegister) { Text("Create account") }
        }
        Text(if (tokenReady) "Secure token ready" else status, color = if (tokenReady) Accent else TextMuted)
    }
}

@Composable
fun CreateSessionCard(
    displayName: String,
    sessionType: String,
    onNameChange: (String) -> Unit,
    onTypeChange: (String) -> Unit,
    onCreate: () -> Unit
) {
    AppCard {
        Text("Start a personal session", color = TextPrimary, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
        OutlinedTextField(value = displayName, onValueChange = onNameChange, label = { Text("Name") }, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(value = sessionType, onValueChange = onTypeChange, label = { Text("Session type") }, modifier = Modifier.fillMaxWidth())
        Button(onClick = onCreate, modifier = Modifier.fillMaxWidth()) { Text("Create local session") }
    }
}

@Composable
fun DevicePlanCard() {
    AppCard {
        Text("Device plan", color = TextPrimary, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
        Bullet("FIT-capable wearable and compatible HR strap")
        Bullet("Pulse oximeter CSV or manual SpO2 entry")
        Bullet("Optional notes: sleep, stress, training, HBOT, sauna")
    }
}

@Composable
fun PhaseCard(metrics: List<PhaseMetric>) {
    AppCard {
        Text("Before / During / After", color = TextPrimary, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
        metrics.forEach { metric ->
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(metric.phase, color = TextPrimary, fontWeight = FontWeight.Bold)
                Text(metric.heartRate, color = TextMuted)
                Text(metric.hrv, color = TextMuted)
                Text(metric.spo2, color = TextMuted)
            }
        }
    }
}

@Composable
fun SessionCard(session: PhysiologySession) {
    AppCard {
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Column {
                Text(session.sessionType, color = TextPrimary, fontWeight = FontWeight.Bold)
                Text(session.status, color = TextMuted)
            }
            Text("${session.recoveryScore}/100", color = Accent, fontWeight = FontWeight.Bold)
        }
        LinearProgressIndicator(progress = { session.matchRate }, modifier = Modifier.fillMaxWidth())
        Text("Data quality ${(session.matchRate * 100).toInt()}% · PDF summary available after sync", color = TextMuted)
    }
}

@Composable
fun ResearchDisclaimer() {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .background(PanelSoft, RoundedCornerShape(10.dp))
            .padding(14.dp)
    ) {
        Text(
            "Research-only wellness insight. CoreLabTech Recovery is not a medical device and does not diagnose, treat or prevent disease.",
            color = TextMuted
        )
    }
}

@Composable
fun Bullet(text: String) {
    Text("• $text", color = TextMuted)
}

@Composable
fun StatusPill(text: String) {
    Box(
        modifier = Modifier
            .background(Color(0xFF064E3B), RoundedCornerShape(999.dp))
            .padding(horizontal = 12.dp, vertical = 8.dp)
    ) {
        Text(text, color = Accent, fontWeight = FontWeight.Bold)
    }
}

@Composable
fun AppCard(content: @Composable Column.() -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = Panel),
        shape = RoundedCornerShape(14.dp)
    ) {
        Column(modifier = Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(10.dp), content = content)
    }
}

fun mobileAuthRequest(
    path: String,
    email: String,
    password: String,
    displayName: String,
    onResult: (String?, String) -> Unit
) {
    Thread {
        try {
            val url = URL("${ApiConfig.BASE_URL}$path")
            val connection = (url.openConnection() as HttpURLConnection).apply {
                requestMethod = "POST"
                setRequestProperty("Content-Type", "application/json")
                doOutput = true
            }
            val body = JSONObject().apply {
                put("email", email)
                put("password", password)
                if (path.endsWith("/register")) {
                    put("display_name", displayName)
                    put("role", "athlete")
                }
            }
            OutputStreamWriter(connection.outputStream).use { it.write(body.toString()) }
            val responseText = connection.inputStream.bufferedReader().use { it.readText() }
            val response = JSONObject(responseText)
            val token = response.optString("access_token", null)
            val role = response.optString("role", "user")
            Handler(Looper.getMainLooper()).post {
                onResult(token, "Authenticated as $role")
            }
        } catch (error: Exception) {
            Handler(Looper.getMainLooper()).post {
                onResult(null, "Sync unavailable: ${error.message}")
            }
        }
    }.start()
}
'@

$iosModels = @'
import Foundation

enum SessionStatus: String, Codable, CaseIterable {
    case baseline = "baseline"
    case ready = "ready"
    case elevatedLoad = "elevated load"
    case watchLoad = "watch load"
    case recoveryTrend = "recovery trend"
    case dataQualityWarning = "data quality warning"
}

struct PhysiologySession: Identifiable, Codable {
    let id: String
    var athleteName: String
    var sessionType: String
    var status: SessionStatus
    var matchRate: Double
    var recoveryScore: Int
    var createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id
        case athleteName
        case sessionType
        case status
        case matchRate
        case recoveryScore
        case createdAt
    }

    init(
        id: String,
        athleteName: String,
        sessionType: String,
        status: SessionStatus,
        matchRate: Double,
        recoveryScore: Int,
        createdAt: Date
    ) {
        self.id = id
        self.athleteName = athleteName
        self.sessionType = sessionType
        self.status = status
        self.matchRate = matchRate
        self.recoveryScore = recoveryScore
        self.createdAt = createdAt
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        athleteName = try container.decode(String.self, forKey: .athleteName)
        sessionType = try container.decode(String.self, forKey: .sessionType)
        status = try container.decodeIfPresent(SessionStatus.self, forKey: .status) ?? .baseline
        matchRate = try container.decodeIfPresent(Double.self, forKey: .matchRate) ?? 0
        recoveryScore = try container.decodeIfPresent(Int.self, forKey: .recoveryScore) ?? Int((matchRate * 100).rounded())
        createdAt = try container.decodeIfPresent(Date.self, forKey: .createdAt) ?? Date()
    }
}

struct PhaseMetric: Identifiable {
    let id = UUID()
    let phase: String
    let heartRate: String
    let hrv: String
    let spo2: String
}

struct DeviceChecklistItem: Identifiable {
    let id = UUID()
    let title: String
    let detail: String
}

struct AuthSession: Codable {
    let accessToken: String
    let tokenType: String
    let userId: String
    let email: String
    let role: String
    let displayName: String

    enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case tokenType = "token_type"
        case userId = "user_id"
        case email
        case role
        case displayName = "display_name"
    }
}
'@

$iosContent = @'
import SwiftUI

struct ContentView: View {
    @State private var displayName = "Alex"
    @State private var sessionType = "Recovery Check"
    @State private var email = "client@example.com"
    @State private var password = "CoreLabTech123"
    @State private var authSession: AuthSession?
    @State private var backendMessage = "Sign in to sync sessions"
    @State private var sessions: [PhysiologySession] = [
        PhysiologySession(id: "ios-demo-001", athleteName: "Alex", sessionType: "HBOT Recovery", status: .ready, matchRate: 0.94, recoveryScore: 86, createdAt: Date()),
        PhysiologySession(id: "ios-demo-002", athleteName: "Alex", sessionType: "Post Training", status: .watchLoad, matchRate: 0.81, recoveryScore: 72, createdAt: Date())
    ]

    private let metrics = [
        PhaseMetric(phase: "Before", heartRate: "64 bpm", hrv: "72 ms", spo2: "98%"),
        PhaseMetric(phase: "During", heartRate: "88 bpm", hrv: "51 ms", spo2: "96%"),
        PhaseMetric(phase: "After", heartRate: "69 bpm", hrv: "68 ms", spo2: "98%")
    ]

    private let checklist = [
        DeviceChecklistItem(title: "Wearable signal", detail: "FIT-capable wearable and compatible HR strap"),
        DeviceChecklistItem(title: "Oxygenation", detail: "Pulse oximeter CSV or manual SpO2 entry"),
        DeviceChecklistItem(title: "Context", detail: "Sleep, stress, training, HBOT, sauna or breathwork notes")
    ]

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {
                    HeroCard()
                    ReadinessCard(score: 86, status: "Ready for light recovery work")
                    AccountSyncCard()
                    StartSessionCard()
                    DevicePlanCard(items: checklist)
                    PhaseSummaryCard(metrics: metrics)
                    RecentSessionsCard(sessions: sessions)
                    DisclaimerCard()
                }
                .padding(18)
            }
            .background(Color.coreBackground)
            .navigationTitle("CoreLabTech")
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    private func createLocalSession() {
        let session = PhysiologySession(
            id: UUID().uuidString,
            athleteName: displayName,
            sessionType: sessionType,
            status: .ready,
            matchRate: 0.90,
            recoveryScore: 82,
            createdAt: Date()
        )
        sessions.insert(session, at: 0)
    }

    private func login() {
        Task {
            do {
                authSession = try await APIClient().login(email: email, password: password)
                backendMessage = "Synced as \(authSession?.role ?? "user")"
            } catch {
                backendMessage = "Sync unavailable: \(error.localizedDescription)"
            }
        }
    }

    private func register() {
        Task {
            do {
                authSession = try await APIClient().register(email: email, password: password, displayName: displayName)
                backendMessage = "Account ready"
            } catch {
                backendMessage = "Account setup failed: \(error.localizedDescription)"
            }
        }
    }

    @ViewBuilder
    private func HeroCard() -> some View {
        AppCard {
            Text("CoreLabTech Recovery")
                .font(.caption.weight(.bold))
                .foregroundStyle(.coreAccent)
            Text("Personal recovery tracker")
                .font(.largeTitle.bold())
                .foregroundStyle(.white)
            Text("Connect wearable FIT data, pulse oximeter readings and session notes to understand how your body responds before, during and after recovery.")
                .foregroundStyle(.coreMuted)
            HStack {
                Button("Start Session", action: createLocalSession)
                    .buttonStyle(.borderedProminent)
                Button("Import FIT/CSV") {}
                    .buttonStyle(.bordered)
            }
        }
    }

    @ViewBuilder
    private func ReadinessCard(score: Int, status: String) -> some View {
        AppCard {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Today readiness")
                        .foregroundStyle(.coreMuted)
                    Text("\(score)")
                        .font(.system(size: 52, weight: .bold))
                        .foregroundStyle(.white)
                }
                Spacer()
                Text(status)
                    .font(.caption.weight(.bold))
                    .foregroundStyle(.coreAccent)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(Color.coreAccent.opacity(0.12), in: Capsule())
            }
            ProgressView(value: Double(score), total: 100)
            Text("Based on HR, HRV, SpO2 and data quality. Not a medical diagnosis.")
                .font(.footnote)
                .foregroundStyle(.coreMuted)
        }
    }

    @ViewBuilder
    private func AccountSyncCard() -> some View {
        AppCard {
            Text("Account sync")
                .font(.headline)
                .foregroundStyle(.white)
            TextField("Email", text: $email)
                .textInputAutocapitalization(.never)
                .textFieldStyle(.roundedBorder)
            SecureField("Password", text: $password)
                .textFieldStyle(.roundedBorder)
            HStack {
                Button("Login", action: login)
                    .buttonStyle(.borderedProminent)
                Button("Create account", action: register)
                    .buttonStyle(.bordered)
            }
            Text(authSession == nil ? backendMessage : "Secure token ready")
                .font(.footnote)
                .foregroundStyle(authSession == nil ? .coreMuted : .coreAccent)
        }
    }

    @ViewBuilder
    private func StartSessionCard() -> some View {
        AppCard {
            Text("Start a personal session")
                .font(.headline)
                .foregroundStyle(.white)
            TextField("Name", text: $displayName)
                .textFieldStyle(.roundedBorder)
            TextField("Session type", text: $sessionType)
                .textFieldStyle(.roundedBorder)
            Button("Create local session", action: createLocalSession)
                .buttonStyle(.borderedProminent)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

struct DevicePlanCard: View {
    let items: [DeviceChecklistItem]

    var body: some View {
        AppCard {
            Text("Device plan")
                .font(.headline)
                .foregroundStyle(.white)
            ForEach(items) { item in
                VStack(alignment: .leading, spacing: 3) {
                    Text(item.title)
                        .font(.subheadline.weight(.bold))
                        .foregroundStyle(.white)
                    Text(item.detail)
                        .font(.footnote)
                        .foregroundStyle(.coreMuted)
                }
            }
        }
    }
}

struct PhaseSummaryCard: View {
    let metrics: [PhaseMetric]

    var body: some View {
        AppCard {
            Text("Before / During / After")
                .font(.headline)
                .foregroundStyle(.white)
            ForEach(metrics) { metric in
                HStack {
                    Text(metric.phase)
                        .font(.subheadline.weight(.bold))
                        .foregroundStyle(.white)
                    Spacer()
                    Text(metric.heartRate)
                    Text(metric.hrv)
                    Text(metric.spo2)
                }
                .font(.footnote)
                .foregroundStyle(.coreMuted)
            }
        }
    }
}

struct RecentSessionsCard: View {
    let sessions: [PhysiologySession]

    var body: some View {
        AppCard {
            Text("Recent recovery sessions")
                .font(.headline)
                .foregroundStyle(.white)
            ForEach(sessions) { session in
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        VStack(alignment: .leading) {
                            Text(session.sessionType)
                                .font(.subheadline.weight(.bold))
                                .foregroundStyle(.white)
                            Text(session.status.rawValue)
                                .font(.footnote)
                                .foregroundStyle(.coreMuted)
                        }
                        Spacer()
                        Text("\(session.recoveryScore)/100")
                            .font(.headline)
                            .foregroundStyle(.coreAccent)
                    }
                    ProgressView(value: session.matchRate)
                    Text("Data quality \(Int(session.matchRate * 100))% · PDF summary available after sync")
                        .font(.caption)
                        .foregroundStyle(.coreMuted)
                }
                .padding(.vertical, 8)
            }
        }
    }
}

struct DisclaimerCard: View {
    var body: some View {
        Text("Research-only wellness insight. CoreLabTech Recovery is not a medical device and does not diagnose, treat or prevent disease.")
            .font(.footnote)
            .foregroundStyle(.coreMuted)
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.corePanelSoft, in: RoundedRectangle(cornerRadius: 12))
    }
}

struct AppCard<Content: View>: View {
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            content
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.corePanel, in: RoundedRectangle(cornerRadius: 16))
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(Color.white.opacity(0.08), lineWidth: 1)
        )
    }
}

private extension Color {
    static let coreBackground = Color(red: 0.043, green: 0.059, blue: 0.102)
    static let corePanel = Color(red: 0.008, green: 0.024, blue: 0.09)
    static let corePanelSoft = Color(red: 0.027, green: 0.067, blue: 0.122)
    static let coreAccent = Color(red: 0.0, green: 1.0, blue: 0.8)
    static let coreMuted = Color(red: 0.714, green: 0.773, blue: 0.839)
}
'@

$androidReadme = @'
# CoreLabTech Recovery - Android

Consumer Android client for personal recovery sessions. This build is focused
on individual users, not QA/performance testing dashboards.

## Product Positioning

CoreLabTech Recovery helps users understand how their body responds before,
during and after recovery routines such as HBOT, sauna, breathwork, training
recovery or daily readiness checks.

The app is research-only wellness software. It is not a medical device and does
not diagnose, treat or prevent disease.

## Main Experience

- Today readiness score.
- Start a personal session.
- FIT-compatible wearable readiness.
- Pulse oximeter SpO2 input or CSV import.
- Before / During / After summary.
- Recovery session history.
- PDF summary after backend sync.

## Android Implementation Notes

- Kotlin + Jetpack Compose.
- Shared FastAPI mobile backend in `../backend`.
- Bearer token auth.
- Production token storage should use Android Keystore or
  EncryptedSharedPreferences.
- File import should use Android document picker and content URI handling.

## Excluded From Consumer App

- Playwright QA dashboards.
- Performance test dashboards.
- Admin database diagnostics.
- Research operator-only controls.

These modules remain in the internal platform, not in the consumer mobile app.
'@

$iosReadme = @'
# CoreLabTech Recovery - iOS

Consumer SwiftUI client for personal recovery sessions. This build is designed
for individual users who want simple recovery insight from wearable FIT data,
SpO2 readings and session notes.

## Product Positioning

CoreLabTech Recovery helps users track how their physiology changes before,
during and after recovery routines such as HBOT, sauna, breathwork, training
recovery or daily readiness checks.

The app is research-only wellness software. It is not a medical device and does
not diagnose, treat or prevent disease.

## Main Experience

- Today readiness score.
- Start a personal session.
- FIT-compatible wearable readiness.
- Pulse oximeter SpO2 input or CSV import.
- Before / During / After summary.
- Recovery session history.
- PDF summary after backend sync.

## iOS Implementation Notes

- SwiftUI native client.
- Shared FastAPI mobile backend in `../backend`.
- Bearer token auth.
- Production token storage should use Keychain.
- File import should use document picker for FIT, CSV and exported wellness
  files.

## Excluded From Consumer App

- Playwright QA dashboards.
- Performance test dashboards.
- Admin database diagnostics.
- Research operator-only controls.

These modules remain in the internal platform, not in the consumer mobile app.
'@

$productDoc = @'
# CoreLabTech Mobile Product Brief

## Consumer Promise

CoreLabTech Recovery turns FIT-compatible wearable data, pulse oximeter readings and
session notes into a simple personal recovery timeline.

The consumer app should answer one question:

> Did my body respond well, and am I recovering normally for me?

## Target Users

- Private HBOT users.
- Athletes and active recovery users.
- Biohacking and longevity users.
- Sauna, breathwork and cold/heat exposure users.
- Coaches or specialists reviewing client data.

## Consumer Features

- Today readiness score.
- Before / During / After session capture.
- FIT import path for compatible wearable devices.
- Pulse oximeter SpO2 and pulse import path.
- Data quality check.
- Recovery trend history.
- PDF summary for personal archive or specialist review.

## What Is Intentionally Removed

- Playwright QA.
- Performance tests.
- Admin database tools.
- Internal mission logs.
- Raw engineering diagnostics.

## Store Positioning

Short description:

Personal recovery tracker for FIT-compatible wearables, SpO2 and session trends.

Long description:

CoreLabTech Recovery helps you track recovery sessions using heart rate, HRV,
SpO2, pulse and context notes. Compare your body response before, during and
after sessions, watch trend changes and export a research-only summary.

Compliance wording:

CoreLabTech Recovery provides research-only wellness insights. It is not a
medical device and does not provide diagnosis, treatment or emergency alerts.
'@

Set-Content -LiteralPath "$Root\Android\app\src\main\java\com\corelabtech\mobile\MainActivity.kt" -Value $androidMain -Encoding UTF8
Set-Content -LiteralPath "$Root\iOS\CoreLabTechMobile\App\Models.swift" -Value $iosModels -Encoding UTF8
Set-Content -LiteralPath "$Root\iOS\CoreLabTechMobile\App\ContentView.swift" -Value $iosContent -Encoding UTF8
Set-Content -LiteralPath "$Root\Android\README.md" -Value $androidReadme -Encoding UTF8
Set-Content -LiteralPath "$Root\iOS\README.md" -Value $iosReadme -Encoding UTF8
Set-Content -LiteralPath "$Root\MOBILE_PRODUCT_BRIEF.md" -Value $productDoc -Encoding UTF8

Write-Output "CoreLabTech mobile consumer update complete."
