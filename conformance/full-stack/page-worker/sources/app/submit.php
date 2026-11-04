<?php
function submit(array $request, $queue): array {
    if (!isset($request['tenant'])) {
        return ['status' => 'rejected'];
    }
    $payload = ['schema' => 'job-v1', 'tenant' => $request['tenant'], 'job' => $request['job']];
    $queue->publish('reports', $payload);
    return ['status' => 'accepted'];
}
