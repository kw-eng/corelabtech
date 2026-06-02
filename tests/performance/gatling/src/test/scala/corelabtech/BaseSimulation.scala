package corelabtech

import io.gatling.core.Predef._
import io.gatling.http.Predef._

trait BaseSimulation {

  val baseUrl: String =
    System.getProperty("baseUrl", "http://127.0.0.1:5000")

  val testSessionId: String =
    System.getProperty("sessionId", "e2euser_1778744307548")

  val httpProtocol = http
    .baseUrl(baseUrl)
    .acceptHeader("application/json")
    .contentTypeHeader("application/json")
    .userAgentHeader("CoreLabTech-Gatling")

  val defaultPauseSeconds = 1
}