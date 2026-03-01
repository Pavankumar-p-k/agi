using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Management;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Windows.Forms;

namespace JarvisLauncher
{
    internal static class Program
    {
        private static readonly string ProjectRoot = ResolveProjectRoot();
        private static readonly string BackendDir = Path.Combine(ProjectRoot, "backend");
        private static readonly string BackendPython = Path.Combine(BackendDir, @"venv\Scripts\python.exe");
        private static readonly string AppExe = Path.Combine(
            ProjectRoot,
            @"jarvis_app\build\windows\x64\runner\Release\jarvis_app.exe"
        );
        private static readonly string LogPath = Path.Combine(ProjectRoot, @"run_logs\launcher.log");
        private static readonly string BackendOutLog = Path.Combine(ProjectRoot, @"run_logs\backend-launcher.out.log");
        private static readonly string BackendErrLog = Path.Combine(ProjectRoot, @"run_logs\backend-launcher.err.log");
        private static readonly object LogLock = new object();

        private static string ResolveProjectRoot()
        {
            var candidates = new List<string>();

            string envRoot = Environment.GetEnvironmentVariable("JARVIS_PROJECT_ROOT");
            if (!string.IsNullOrWhiteSpace(envRoot))
            {
                candidates.Add(envRoot);
            }

            candidates.Add(AppDomain.CurrentDomain.BaseDirectory);
            candidates.Add(Directory.GetCurrentDirectory());

            foreach (string baseDir in candidates.Where(c => !string.IsNullOrWhiteSpace(c)))
            {
                string normalized = Path.GetFullPath(baseDir);
                for (int i = 0; i < 6; i++)
                {
                    if (LooksLikeProjectRoot(normalized))
                    {
                        return normalized;
                    }

                    string parent = Path.GetDirectoryName(normalized);
                    if (string.IsNullOrWhiteSpace(parent) || parent == normalized)
                    {
                        break;
                    }
                    normalized = parent;
                }
            }

            return @"C:\Users\Pavan\desktop\apk\jarvis-project";
        }

        private static bool LooksLikeProjectRoot(string path)
        {
            if (string.IsNullOrWhiteSpace(path))
            {
                return false;
            }

            return Directory.Exists(Path.Combine(path, "backend"))
                && Directory.Exists(Path.Combine(path, "jarvis_app"));
        }

        [STAThread]
        private static void Main()
        {
            bool createdNew;
            using (var mutex = new Mutex(initiallyOwned: true, name: @"Global\JarvisOneClickLauncher", createdNew: out createdNew))
            {
                if (!createdNew)
                {
                    MessageBox.Show(
                        "JARVIS launcher is already running. Please wait a few seconds.",
                        "JARVIS Launcher",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Information
                    );
                    return;
                }

                Directory.CreateDirectory(Path.GetDirectoryName(LogPath) ?? ProjectRoot);
                Log("Launcher started.");

                try
                {
                    bool backendHealthy = EnsureBackendRunning();
                    EnsureDesktopAppRunning();
                    if (!backendHealthy)
                    {
                        MessageBox.Show(
                            "Backend is still starting. Desktop app is open, but server features may take up to 2 minutes to respond.",
                            "JARVIS Launcher",
                            MessageBoxButtons.OK,
                            MessageBoxIcon.Warning
                        );
                    }
                    Log("Launcher finished successfully.");
                }
                catch (Exception ex)
                {
                    Log("Fatal error: " + ex);
                    MessageBox.Show(
                        "JARVIS launcher failed.\n\n" + ex.Message,
                        "JARVIS Launcher",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Error
                    );
                }
                finally
                {
                    Log("Launcher exiting.");
                    Environment.Exit(0);
                }
            }
        }

        private static bool EnsureBackendRunning()
        {
            if (IsBackendHealthy())
            {
                Log("Backend already healthy on http://127.0.0.1:8000.");
                return true;
            }

            int runningPid = FindBackendProcessId();
            if (runningPid > 0)
            {
                Log("Found existing backend process PID=" + runningPid + ". Waiting for health.");
                return WaitForBackendHealthy(TimeSpan.FromSeconds(120));
            }

            if (IsTcpPortOpen("127.0.0.1", 8000))
            {
                Log("Port 8000 is already open. Waiting for /health.");
                return WaitForBackendHealthy(TimeSpan.FromSeconds(60));
            }

            string pythonExe = File.Exists(BackendPython) ? BackendPython : "python";
            Log("Starting backend with: " + pythonExe + " -u -m core.main");

            var psi = new ProcessStartInfo
            {
                FileName = pythonExe,
                Arguments = "-u -m core.main",
                WorkingDirectory = BackendDir,
                UseShellExecute = false,
                CreateNoWindow = true,
                WindowStyle = ProcessWindowStyle.Hidden,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                StandardOutputEncoding = Encoding.UTF8,
                StandardErrorEncoding = Encoding.UTF8
            };

            var proc = new Process
            {
                StartInfo = psi,
                EnableRaisingEvents = true
            };
            proc.OutputDataReceived += (_, e) =>
            {
                if (!string.IsNullOrWhiteSpace(e.Data))
                {
                    AppendLine(BackendOutLog, e.Data);
                }
            };
            proc.ErrorDataReceived += (_, e) =>
            {
                if (!string.IsNullOrWhiteSpace(e.Data))
                {
                    AppendLine(BackendErrLog, e.Data);
                }
            };

            proc.Start();
            proc.BeginOutputReadLine();
            proc.BeginErrorReadLine();
            if (proc != null)
            {
                Log("Backend process started. PID=" + proc.Id);
            }

            return WaitForBackendHealthy(TimeSpan.FromSeconds(120));
        }

        private static bool WaitForBackendHealthy(TimeSpan timeout)
        {
            DateTime until = DateTime.UtcNow.Add(timeout);
            while (DateTime.UtcNow < until)
            {
                if (IsBackendHealthy())
                {
                    Log("Backend became healthy.");
                    return true;
                }
                Thread.Sleep(1500);
            }

            Log("Backend did not become healthy within " + (int)timeout.TotalSeconds + " seconds.");
            return false;
        }

        private static void EnsureDesktopAppRunning()
        {
            if (!File.Exists(AppExe))
            {
                throw new FileNotFoundException("Desktop app executable not found.", AppExe);
            }

            if (Process.GetProcessesByName("jarvis_app").Any())
            {
                Log("Desktop app already running.");
                return;
            }

            Log("Starting desktop app: " + AppExe);
            var psi = new ProcessStartInfo
            {
                FileName = AppExe,
                WorkingDirectory = Path.GetDirectoryName(AppExe) ?? ProjectRoot,
                UseShellExecute = true,
                WindowStyle = ProcessWindowStyle.Normal
            };
            Process.Start(psi);
        }

        private static int FindBackendProcessId()
        {
            try
            {
                using (var searcher =
                    new ManagementObjectSearcher("SELECT ProcessId, Name, CommandLine FROM Win32_Process WHERE Name = 'python.exe' OR Name = 'pythonw.exe'"))
                {
                    foreach (ManagementObject process in searcher.Get())
                    {
                        string commandLine = (process["CommandLine"] as string) ?? string.Empty;
                        if (commandLine.IndexOf("core.main", StringComparison.OrdinalIgnoreCase) >= 0
                            && commandLine.IndexOf(BackendDir, StringComparison.OrdinalIgnoreCase) >= 0)
                        {
                            return Convert.ToInt32(process["ProcessId"]);
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                Log("FindBackendProcessId failed: " + ex.Message);
            }
            return 0;
        }

        private static bool IsTcpPortOpen(string host, int port)
        {
            try
            {
                using (var client = new TcpClient())
                {
                    var connectTask = client.ConnectAsync(host, port);
                    bool connected = connectTask.Wait(TimeSpan.FromMilliseconds(800));
                    return connected && client.Connected;
                }
            }
            catch
            {
                return false;
            }
        }

        private static bool IsBackendHealthy()
        {
            try
            {
                var request = (HttpWebRequest)WebRequest.Create("http://127.0.0.1:8000/health");
                request.Method = "GET";
                request.Timeout = 2000;
                request.ReadWriteTimeout = 2000;
                request.Proxy = null;
                using (var response = (HttpWebResponse)request.GetResponse())
                {
                    return response.StatusCode == HttpStatusCode.OK;
                }
            }
            catch
            {
                return false;
            }
        }

        private static void Log(string line)
        {
            AppendLine(LogPath, line);
        }

        private static void AppendLine(string path, string line)
        {
            const int MaxAttempts = 4;
            for (int attempt = 1; attempt <= MaxAttempts; attempt++)
            {
                try
                {
                    lock (LogLock)
                    {
                        Directory.CreateDirectory(Path.GetDirectoryName(path) ?? ProjectRoot);
                        using (var stream = new FileStream(path, FileMode.Append, FileAccess.Write, FileShare.ReadWrite))
                        using (var writer = new StreamWriter(stream, Encoding.UTF8))
                        {
                            writer.WriteLine(DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + " " + line);
                        }
                    }
                    return;
                }
                catch (IOException)
                {
                    Thread.Sleep(50 * attempt);
                }
                catch (UnauthorizedAccessException)
                {
                    Thread.Sleep(50 * attempt);
                }
                catch
                {
                    return;
                }
            }
        }
    }
}
