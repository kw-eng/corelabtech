package corelabtech

import io.gatling.core.Predef._
import io.gatling.http.Predef._
import scala.concurrent.duration._

class UploadCsvSimulation extends Simulation with BaseSimulation {

  val csvBody: String =
    """timestamp,pulse,spo2
      |2026-01-01T10:00:00,58,98
      |2026-01-01T10:00:01,59,98
      |2026-01-01T10:00:02,60,98
      |2026-01-01T10:00:03,61,99
      |2026-01-01T10:00:04,62,98
      |2026-01-01T10:00:05,63,98
      |2026-01-01T10:00:06,64,97
      |2026-01-01T10:00:07,65,98
      |2026-01-01T10:00:08,66,98
      |2026-01-01T10:00:09,67,99
      |""".stripMargin

  val scn = scenario("CSV Upload Performance Test")
    .exec(
      http("POST /upload_csv")
        .post("/upload_csv")
        .formParam("session_id", "GATLING_CSV_UPLOAD_SESSION")
        .bodyPart(
          StringBodyPart("file", csvBody)
            .fileName("gatling_sample.csv")
            .contentType("text/csv")
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
      global.responseTime.percentile3.lt(2000),
      global.failedRequests.percent.lt(20)
    )
}