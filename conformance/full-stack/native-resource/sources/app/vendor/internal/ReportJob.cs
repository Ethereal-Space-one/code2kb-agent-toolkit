using System.Diagnostics;
using System.IO;

public static class ReportJob {
    public static int Run(string output) {
        string temporary = output + ".tmp";
        File.WriteAllText(temporary, "report");
        using var process = Process.Start(new ProcessStartInfo("report-helper", temporary) { UseShellExecute = false });
        if (process is null) throw new IOException("not started");
        process.WaitForExit();
        if (process.ExitCode != 0) return process.ExitCode;
        File.Delete(temporary);
        return 0;
    }
}
