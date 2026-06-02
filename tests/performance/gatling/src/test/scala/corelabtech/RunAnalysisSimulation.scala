package corelabtech

import io.gatling.core.Predef._
import io.gatling.http.Predef._
import scala.concurrent.duration._

class RunAnalysisSimulation extends Simulation with BaseSimulation {

  val requestBody: String =
    """{
      |  "session_id": "E2E_DEMO_1779831334754"
      |}""".stripMargin

  val scn = scenario("AI Run Analysis Performance Test")
    .exec(
      http("POST /api/run_analysis")
        .post("/api/run_analysis")
        .body(StringBody(requestBody))
        .asJson
        .check(status.in(200, 302, 400, 404, 500))
    )
    .pause(defaultPauseSeconds)

  setUp(
    scn.inject(
      rampUsers(10).during(20.seconds),
      constantUsersPerSec(2).during(30.seconds)
    )
  )
    .protocols(httpProtocol)
    .assertions(
      global.responseTime.percentile3.lt(1500),
      global.failedRequests.percent.lt(20)
    )
}