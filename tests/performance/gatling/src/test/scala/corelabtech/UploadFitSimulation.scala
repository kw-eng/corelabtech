package corelabtech

import io.gatling.core.Predef._
import io.gatling.http.Predef._
import scala.concurrent.duration._

class UploadFitSimulation extends Simulation with BaseSimulation {

  val fakeFitBody: String =
    "FAKE_FIT_PERFORMANCE_TEST_DATA_FOR_ENDPOINT_STABILITY"

  val scn = scenario("FIT Upload Performance Test")
    .exec(
      http("POST /upload_fit")
        .post("/upload_fit")
        .formParam("session_id", "GATLING_FIT_UPLOAD_SESSION")
        .bodyPart(
          StringBodyPart("file", fakeFitBody)
            .fileName("gatling_sample.fit")
            .contentType("application/octet-stream")
        )
        .asMultipartForm
        .check(status.in(200, 400, 500))
    )
    .pause(defaultPauseSeconds)

  setUp(
    scn.inject(
      rampUsers(5).during(20.seconds),
      constantUsersPerSec(1).during(30.seconds)
    )
  )
    .protocols(httpProtocol)
    .assertions(
      global.responseTime.percentile3.lt(2500),
      global.failedRequests.percent.lt(20)
    )
}