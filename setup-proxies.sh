#!/bin/bash

TOXI="http://localhost:8474"

echo "Waiting for Toxiproxy to be ready..."
sleep 2

echo "Cleaning old proxies..."
curl -s $TOXI/proxies | jq -r '.proxies[].name' 2>/dev/null | while read p; do
  curl -s -X DELETE $TOXI/proxies/$p > /dev/null
done

create_proxy () {
  NAME=$1
  LISTEN_PORT=$2
  UPSTREAM=$3

  echo "Creating proxy: $NAME"
  curl -s -X POST $TOXI/proxies \
  -H "Content-Type: application/json" \
  -d "{
        \"name\": \"$NAME\",
        \"listen\": \"0.0.0.0:$LISTEN_PORT\",
        \"upstream\": \"$UPSTREAM\"
      }" > /dev/null
}

# Random latency
add_latency () {
  NAME=$1
  LATENCY=$((RANDOM % 300 + 100))  # 100–400 ms
  JITTER=$((RANDOM % 50))          # 0–50 ms

  echo "Adding latency to $NAME → ${LATENCY}ms ± ${JITTER}ms"

  curl -s -X POST $TOXI/proxies/$NAME/toxics \
  -H "Content-Type: application/json" \
  -d "{
        \"name\": \"latency\",
        \"type\": \"latency\",
        \"attributes\": {
          \"latency\": $LATENCY,
          \"jitter\": $JITTER
        }
      }" > /dev/null
}

echo "Creating region-to-region proxies..."

# Mumbai → others
create_proxy "mumbai_to_virginia" 8666 "virginia:5000"
create_proxy "mumbai_to_frankfurt" 8667 "frankfurt:5000"

# Virginia → others
create_proxy "virginia_to_mumbai" 8668 "mumbai:5000"
create_proxy "virginia_to_frankfurt" 8669 "frankfurt:5000"

# Frankfurt → others
create_proxy "frankfurt_to_mumbai" 8670 "mumbai:5000"
create_proxy "frankfurt_to_virginia" 8671 "virginia:5000"

echo "Injecting random latency..."

add_latency "mumbai_to_virginia"
add_latency "mumbai_to_frankfurt"
add_latency "virginia_to_mumbai"
add_latency "virginia_to_frankfurt"
add_latency "frankfurt_to_mumbai"
add_latency "frankfurt_to_virginia"

echo "Done. Latency injection complete."