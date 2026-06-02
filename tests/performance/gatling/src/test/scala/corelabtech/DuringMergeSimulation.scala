package corelabtech

import io.gatling.core.Predef._
import io.gatling.http.Predef._
import scala.concurrent.duration._

class DuringMergeSimulation extends Simulation with BaseSimulation {

  val scn = scenario("During Merge Performance Test")
    .exec(
      http("POST /api/during_merge")
        .post("/api/during_merge")
        .body(StringBody(
          s"""
          {
            "session_id": "$testSessionId"
          }
          """
        )).asJson
        .check(status.in(200, 404))
    )
    .pause(defaultPauseSeconds)

  setUp(
    scn.inject(
      rampUsers(10).during(20.seconds),
      constantUsersPerSec(3).during(30.seconds)
    )
  )
    .protocols(httpProtocol)
    .assertions(
      global.responseTime.percentile3.lt(1000),
      global.failedRequests.percent.lt(10)
    )
}