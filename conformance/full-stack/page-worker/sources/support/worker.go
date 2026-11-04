package worker

import "errors"

type Message struct {
    Schema string
    Tenant string
    Job string
    Ack func()
}

func Handle(m Message, save func(string, string) error) error {
    m.Ack()
    if m.Schema != "job-v1" {
        return errors.New("unsupported schema")
    }
    if err := save(m.Tenant, m.Job); err != nil {
        return err
    }
    return nil
}
