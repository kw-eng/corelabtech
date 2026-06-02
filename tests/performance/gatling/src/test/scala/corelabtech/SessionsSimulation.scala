package corelabtech

import io.gatling.core.Predef._
import io.gatling.http.Predef._
import scala.concurrent.duration._

class SessionsSimulation extends Simulation {

  val httpProtocol = http
    .baseUrl("http://127.0.0.1:5000")
    .acceptHeader("application/json")

  val scn = scenario("Sessions API Load Test")
    .exec(
      http("GET /api/performance/sessions")
        .get("/api/performance/sessions")
        .check(status.is(200))
        .check(jsonPath("$.status").is("ok"))
        .check(jsonPath("$.sessions").exists)
    )

  setUp(
    scn.inject(
      rampUsers(80).during(60.seconds)
    )
  )
    .protocols(httpProtocol)
    .assertions(
      global.responseTime.percentile3.lt(1000),
      global.successfulRequests.percent.gt(95)
    )
}