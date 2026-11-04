FROM alpine:3.20 AS build
RUN apk add --no-cache build-base
COPY native/helper.c /src/helper.c
RUN cc /src/helper.c -o /report-helper
FROM alpine:3.20
COPY --from=build /report-helper /usr/local/bin/report-helper
