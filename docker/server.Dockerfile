# BioPilot 服务端：多阶段构建（容器内 mvn 打包 → JRE 运行）。
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /src
COPY server/pom.xml ./pom.xml
COPY server/bio-common ./bio-common
COPY server/bio-modules ./bio-modules
COPY server/bio-admin ./bio-admin
RUN mvn -q install -DskipTests

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /src/bio-admin/target/bio-admin-1.0.0.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
