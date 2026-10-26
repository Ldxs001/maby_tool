// SPDX-License-Identifier: AGPL-3.0-or-later
// MDEditor installer (WinForms). Compiled at packaging time by the system
// csc.exe (Windows built-in .NET Framework compiler). No third-party tools.
//
// Embedded resources (added by _build_installer.py):
//   payload.zip  - dist checklist minimum set (UTF-8 entry names, python zipfile)
//   ver.txt      - installer/app version string
//
// Usage:  MDEditor-Setup-vX.Y.Z.exe            (installer GUI)
//         MDEditor-Setup-vX.Y.Z.exe --smoke    (headless self-check, writes
//                                               %TEMP%\md_setup_smoke_report.txt)
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Windows.Forms;
using Microsoft.Win32;

// 程序集元数据：安装包在资源管理器属性面板 / 任务栏「属性」里要有可读信息。
// 版本号由构建脚本写进独立文件（_setup_ver.cs），此处不写死，避免与
// CHANGELOG 版本脱节。
[assembly: AssemblyTitle("MDEditor 安装程序")]
[assembly: AssemblyProduct("MDEditor")]
[assembly: AssemblyDescription("MDEditor 安装程序")]
[assembly: AssemblyCompany("wUwproject")]
[assembly: AssemblyCopyright("Copyright (c) wUwproject")]

namespace MDEditorSetup
{
    static class Setup
    {
        internal const string ResZip = "payload.zip";
        internal const string ResVer = "ver.txt";
        internal static readonly string Version = ReadVersion();

        [STAThread]
        static void Main(string[] args)
        {
            if (args != null && args.Any(a => string.Equals(a, "--smoke", StringComparison.OrdinalIgnoreCase)))
            {
                RunSmoke();
                return;
            }
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new SetupForm());
        }

        static Stream Res(string name)
        {
            var s = typeof(Setup).Assembly.GetManifestResourceStream(name);
            if (s == null) throw new FileNotFoundException("missing resource: " + name);
            return s;
        }

        static string ReadVersion()
        {
            using (var s = Res(ResVer))
            using (var r = new StreamReader(s))
            {
                // ver.txt 格式：第 1 行版本号，第 2 行 payload.zip 的 SHA256。
                var lines = r.ReadToEnd().Split('\n');
                return lines.Length > 0 ? lines[0].Trim() : "";
            }
        }

        // payload 完整性校验：构建期把 payload.zip 的 SHA256 写进 ver.txt 同一份
        // 资源文件（首行版本号、次行摘要），安装期比对。传输损坏或资源被替换
        // 都会被当场拦下，而不是装出一个坏程序。
        static void VerifyPayload()
        {
            string expected;
            using (var s = Res(ResVer))
            using (var r = new StreamReader(s))
            {
                var lines = r.ReadToEnd().Split('\n');
                expected = lines.Length > 1 ? lines[1].Trim() : "";
            }
            if (expected.Length != 64) return;   // 没写摘要就跳过（不拦正常安装）
            string actual;
            using (var s = Res(ResZip))
            using (var sha = System.Security.Cryptography.SHA256.Create())
                actual = BitConverter.ToString(sha.ComputeHash(s)).Replace("-", "").ToLowerInvariant();
            if (!string.Equals(actual, expected, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("payload 校验失败：文件可能未完整下载，请重新下载安装包。");
        }

        internal static ZipArchive OpenPayload()
        {
            // copy to memory so the zip stays usable after the resource stream is disposed
            using (var s = Res(ResZip))
            {
                var ms = new MemoryStream();
                s.CopyTo(ms);
                ms.Position = 0;
                return new ZipArchive(ms, ZipArchiveMode.Read);
            }
        }

        static void ExtractEntry(ZipArchiveEntry entry, string dst)
        {
            var full = Path.GetFullPath(dst);
            // 目录包含判定：StartsWith 前缀法会把 "...\MDEditorEvil\x" 误判为在
            // "...\MDEditor" 之内（zip-slip 绕过），必须带目录分隔符再比。
            var root = _extractRoot.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)
                       + Path.DirectorySeparatorChar;
            if (!full.StartsWith(root, StringComparison.OrdinalIgnoreCase))
                throw new IOException("zip-slip blocked: " + entry.FullName);
            var dir = Path.GetDirectoryName(full);
            if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
            if (entry.Name != "") entry.ExtractToFile(full, true);
        }

        static string _extractRoot = "";

        internal static void ExtractTo(string target, Action<int, int> progress)
        {
            VerifyPayload();
            _extractRoot = Path.GetFullPath(target);
            using (var zip = OpenPayload())
            {
                var entries = zip.Entries.Where(e => e.FullName != "" && !e.FullName.EndsWith("/")).ToList();
                int total = entries.Count, done = 0;
                foreach (var e in entries)
                {
                    ExtractEntry(e, Path.Combine(target, e.FullName.Replace('/', Path.DirectorySeparatorChar)));
                    done++;
                    if (progress != null && (done % 25 == 0 || done == total))
                        progress(done, total);
                }
            }
        }

        static long DirSize(string dir)
        {
            long sum = 0;
            foreach (var f in Directory.GetFiles(dir, "*", SearchOption.AllDirectories))
                sum += new FileInfo(f).Length;
            return sum;
        }

        internal static bool WebView2Present()
        {
            string[] keys = {
                @"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
                @"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
            };
            foreach (var root in new[] { Registry.LocalMachine, Registry.CurrentUser })
                foreach (var k in keys)
                    try { using (var rk = root.OpenSubKey(k)) if (rk != null) return true; } catch { }
            foreach (var p in new[] {
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86), @"Microsoft\EdgeWebView\Application"),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), @"Microsoft\EdgeWebView\Application") })
                try
                {
                    if (Directory.Exists(p) && Directory.GetDirectories(p)
                        .Any(d => { var n = Path.GetFileName(d); return n.Length > 0 && char.IsDigit(n[0]); }))
                        return true;
                } catch { }
            return false;
        }

        static Process RunHidden(string exe, string args, string cwd)
        {
            var psi = new ProcessStartInfo(exe, args)
            {
                UseShellExecute = false,
                CreateNoWindow = true,
                WorkingDirectory = string.IsNullOrEmpty(cwd) ? null : cwd
            };
            var p = Process.Start(psi);
            p.WaitForExit(300000);
            return p;
        }

        static void WriteArpExtras(string target, Action<string> log)
        {
            // install.cmd owns the ARP entry (single source). Here we only
            // supplement the fields only the installer knows: version + size.
            try
            {
                using (var k = Registry.CurrentUser.OpenSubKey(
                    @"Software\Microsoft\Windows\CurrentVersion\Uninstall\MDEditor", true))
                {
                    if (k == null)
                    {
                        log("[!] 卸载条目缺失（install.cmd 未完成第 5 步登记）");
                        return;
                    }
                    k.SetValue("DisplayVersion", Version);
                    k.SetValue("EstimatedSize", (int)Math.Min(DirSize(target) / 1024, (long)int.MaxValue), RegistryValueKind.DWord);
                    log("卸载条目已就绪：设置 → 应用 → \"MDEditor (Markdown Editor)\"。");
                }
            }
            catch (Exception ex) { log("[!] 卸载条目补充失败: " + ex.Message); }
        }

        internal static void Install(string target, Action<string> log, Action<int> pct, Action done, Action<string> fail)
        {
            var bw = new BackgroundWorker { WorkerReportsProgress = true };
            bw.ProgressChanged += (s, e) => pct(e.ProgressPercentage);
            bw.RunWorkerCompleted += (s, e) =>
            {
                if (e.Error != null) fail(e.Error.Message);
                else done();
            };
            bw.DoWork += (s, e) =>
            {
                if (File.Exists(Path.Combine(target, "md_server.py")))
                {
                    log("[升级] 检测到已有安装，先停止运行中的服务...");
                    var stop = Path.Combine(target, "md_stop.cmd");
                    if (File.Exists(stop)) RunHidden("cmd.exe", "/c \"" + stop + "\"", target);
                    else RunHidden("cmd.exe", "/c \"" + Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "md_stop.cmd") + "\"", target);
                    System.Threading.Thread.Sleep(800);
                }
                log("复制文件到 " + target + " ...");
                ExtractTo(target, (d, t) => { bw.ReportProgress(d * 100 / t); log("  " + d + "/" + t); });
                log("系统集成（右键菜单 / 图标 / 快捷方式 / EXE 编译 / 卸载条目登记）...");
                var p = RunHidden("cmd.exe", "/c install.cmd nopause", target);
                log(p.ExitCode == 0 ? "install.cmd 执行成功。" : "[!] install.cmd 退出码 " + p.ExitCode + "（可稍后在安装目录手动重跑）");
                WriteArpExtras(target, log);
                log("");
                log("安装完成：" + target);
                log("右键 .md 文件可用 MDEditor 打开。");
            };
            bw.RunWorkerAsync();
        }

        static void RunSmoke()
        {
            var tmp = Path.Combine(Path.GetTempPath(), "md_setup_smoke");
            try { if (Directory.Exists(tmp)) Directory.Delete(tmp, true); } catch { }
            var lines = new List<string>();
            ExtractTo(tmp, null);
            string docs = Path.Combine(tmp, "docs");
            string guide = Path.Combine(docs, "MDEditor 使用指南.md");
            string lic = Path.Combine(docs, "版权与开源组件声明.md");
            string dll = Path.Combine(tmp, @"python\Lib\site-packages\pythonnet\runtime\Python.Runtime.dll");
            string fonts = Path.Combine(tmp, @"katex\fonts");
            string uico = Path.Combine(tmp, "uninstall-md.ico");
            string ucs = Path.Combine(tmp, "UninstallMDEditor.cs");
            string shim = Path.Combine(tmp, "MarkdownEditor.exe");
            string uninst = Path.Combine(tmp, "UninstallMDEditor.exe");
            string mjs = Path.Combine(tmp, @"mermaid\mermaid.min.js");
            string vjs = Path.Combine(tmp, @"viz\viz-standalone.js");
            string wjs = Path.Combine(tmp, @"wavedrom\wavedrom.min.js");
            string wsk = Path.Combine(tmp, @"wavedrom\skins\default.js");
            string wskd = Path.Combine(tmp, @"wavedrom\skins\dark.js");
            string gejs = Path.Combine(tmp, @"vega\vega-embed.min.js");
            lines.Add("total_files=" + Directory.GetFiles(tmp, "*", SearchOption.AllDirectories).Length);
            lines.Add("guide_md_exists=" + (File.Exists(guide) ? 1 : 0));
            lines.Add("license_doc_exists=" + (File.Exists(lic) ? 1 : 0));
            lines.Add("uninstall_icon_exists=" + (File.Exists(uico) ? 1 : 0));
            lines.Add("uninstaller_cs_exists=" + (File.Exists(ucs) ? 1 : 0));
            lines.Add("shim_exe_exists=" + (File.Exists(shim) ? 1 : 0));
            lines.Add("shim_exe_size=" + (File.Exists(shim) ? new FileInfo(shim).Length : 0));
            lines.Add("uninstaller_exe_exists=" + (File.Exists(uninst) ? 1 : 0));
            lines.Add("uninstaller_exe_size=" + (File.Exists(uninst) ? new FileInfo(uninst).Length : 0));
            lines.Add("docs_listing=" + string.Join(";", Directory.GetFileSystemEntries(docs).Select(Path.GetFileName)));
            lines.Add("pythonnet_dll_size=" + (File.Exists(dll) ? new FileInfo(dll).Length : 0));
            lines.Add("katex_fonts_count=" + (Directory.Exists(fonts) ? Directory.GetFiles(fonts).Length : 0));
            lines.Add("pythonw_exists=" + (File.Exists(Path.Combine(tmp, @"python\pythonw.exe")) ? 1 : 0));
            lines.Add("webview2=" + (WebView2Present() ? 1 : 0));
            lines.Add("mermaid_vendor_size=" + (File.Exists(mjs) ? new FileInfo(mjs).Length : 0));
            lines.Add("viz_vendor_size=" + (File.Exists(vjs) ? new FileInfo(vjs).Length : 0));
            lines.Add("wavedrom_vendor_size=" + (File.Exists(wjs) ? new FileInfo(wjs).Length : 0));
            lines.Add("wavedrom_skin_size=" + (File.Exists(wsk) ? new FileInfo(wsk).Length : 0));
            lines.Add("wavedrom_skin_dark_size=" + (File.Exists(wskd) ? new FileInfo(wskd).Length : 0));
            lines.Add("vega_embed_vendor_size=" + (File.Exists(gejs) ? new FileInfo(gejs).Length : 0));
            lines.Add("version=" + Version);
            File.WriteAllLines(Path.Combine(Path.GetTempPath(), "md_setup_smoke_report.txt"), lines);
            try { Directory.Delete(tmp, true); } catch { }
        }
    }

    // 配色：跟随系统深浅色。深色主题下窗口底色跟系统走，避免白底窗口在深色
    // 桌面里突兀。取值只读系统注册表，不写任何用户配置。
    class Palette
    {
        public Color Canvas;      // 窗口底色
        public Color Surface;     // 卡片 / 输入框底色
        public Color Header;      // 顶栏底色
        public Color HeaderText;  // 顶栏主文字
        public Color HeaderSub;   // 顶栏次要文字
        public Color Text;        // 正文
        public Color TextDim;     // 次要正文
        public Color Border;      // 描边
        public Color Accent;      // 主按钮
        public Color AccentText;
        public Color Ok;          // 状态条：正常
        public Color Warn;        // 状态条：降级
        public bool Dark;
    }

    static class Ui
    {
        internal static readonly Palette Light = new Palette
        {
            Canvas = Color.FromArgb(0xF1, 0xF4, 0xF8),
            Surface = Color.White,
            Header = Color.FromArgb(0x17, 0x26, 0x3F),
            HeaderText = Color.White,
            HeaderSub = Color.FromArgb(0xA6, 0xB6, 0xCD),
            Text = Color.FromArgb(0x1B, 0x24, 0x30),
            TextDim = Color.FromArgb(0x5C, 0x6A, 0x7C),
            Border = Color.FromArgb(0xD2, 0xDA, 0xE5),
            Accent = Color.FromArgb(0x2F, 0x6F, 0xEB),
            AccentText = Color.White,
            Ok = Color.FromArgb(0x1B, 0x8A, 0x4B),
            Warn = Color.FromArgb(0xB5, 0x6A, 0x11),
            Dark = false
        };

        internal static readonly Palette Dark = new Palette
        {
            Canvas = Color.FromArgb(0x15, 0x1A, 0x21),
            Surface = Color.FromArgb(0x1D, 0x24, 0x2E),
            Header = Color.FromArgb(0x0C, 0x11, 0x18),
            HeaderText = Color.FromArgb(0xEC, 0xF1, 0xF7),
            HeaderSub = Color.FromArgb(0x93, 0xA3, 0xB6),
            Text = Color.FromArgb(0xE3, 0xE9, 0xF0),
            TextDim = Color.FromArgb(0x9B, 0xA8, 0xB8),
            Border = Color.FromArgb(0x30, 0x3A, 0x47),
            Accent = Color.FromArgb(0x4C, 0x8D, 0xFF),
            AccentText = Color.FromArgb(0x0C, 0x11, 0x18),
            Ok = Color.FromArgb(0x4C, 0xC3, 0x8C),
            Warn = Color.FromArgb(0xE0, 0xA9, 0x55),
            Dark = true
        };

        internal static Palette Current { get; private set; }

        internal static void Init()
        {
            bool dark = false;
            try
            {
                using (var k = Registry.CurrentUser.OpenSubKey(
                    @"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"))
                {
                    object v = k == null ? null : k.GetValue("AppsUseLightTheme");
                    if (v != null) dark = Convert.ToInt32(v) == 0;
                }
            }
            catch { }
            Current = dark ? Dark : Light;
        }

        // 界面字体：取系统 UI 字体族（Windows 上即「Microsoft YaHei UI」），源码里
        // 不写任何专有字体名，也不在包内附带任何字体文件。GdiCharSet 指定 GB2312 是
        // 给字体链接用的：西文系统上系统 UI 字体没有中文字形，指定字符集后系统会
        // 自动挑一款带中文字形的系统字体接管，不做静默回退到点阵宋体。
        internal static Font FontOf(float size, FontStyle style)
        {
            return new Font(SystemFonts.MessageBoxFont.FontFamily, size, style,
                            GraphicsUnit.Point, 134);
        }

        // 日志区用等宽：ASCII 路径与编号需要对齐；中文由字符集链接接管。
        internal static Font MonoFontOf(float size)
        {
            return new Font(FontFamily.GenericMonospace, size, FontStyle.Regular,
                            GraphicsUnit.Point, 134);
        }
    }

    class SetupForm : Form
    {
        const int WM_DPICHANGED = 0x02E0;

        [StructLayout(LayoutKind.Sequential)]
        struct RECT { public int Left, Top, Right, Bottom; }

        [DllImport("user32.dll")]
        static extern uint GetDpiForWindow(IntPtr hwnd);
        [DllImport("user32.dll")]
        static extern uint GetDpiForSystem();
        [DllImport("user32.dll")]
        static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
        [DllImport("dwmapi.dll")]
        static extern int DwmSetWindowAttribute(IntPtr h, int attr, ref uint val, int size);

        // 设计稿坐标一律按 96 DPI 写，运行期按实际 DPI 换算，控件不手工算像素。
        readonly Dictionary<Control, Rectangle> _design = new Dictionary<Control, Rectangle>();

        readonly TextBox _txtDir = new TextBox();
        readonly TextBox _txtLog = new TextBox();
        readonly ProgressBar _prog = new ProgressBar();
        readonly Button _btnInstall = new Button();
        readonly Button _btnRun = new Button();
        readonly Button _btnBrowse = new Button();
        readonly Button _btnExit = new Button();
        readonly Label _lblStatus = new Label();
        readonly Label _lblTitle = new Label();
        readonly Label _lblSub = new Label();
        readonly Label _lblDir = new Label();
        readonly Panel _pnlHeader = new Panel();
        readonly Panel _pnlStatus = new Panel();
        readonly Panel _pnlDot = new Panel();
        readonly PictureBox _picIcon = new PictureBox();
        readonly GroupBox _grpLog = new GroupBox();
        string _target;
        float _k = 1f;

        public SetupForm()
        {
            Ui.Init();
            var pal = Ui.Current;

            Text = "MDEditor v" + Setup.Version + " 安装程序";
            FormBorderStyle = FormBorderStyle.FixedDialog;
            StartPosition = FormStartPosition.CenterScreen;
            MaximizeBox = false;
            MinimizeBox = false;
            AutoScaleMode = AutoScaleMode.None;   // 缩放由本类自己按 DPI 精确控制
            ClientSize = new Size(640, 540);
            BackColor = pal.Canvas;
            ForeColor = pal.Text;
            Font = Ui.FontOf(9f, FontStyle.Regular);

            try
            {
                var ico = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
                if (ico != null)
                {
                    this.Icon = ico;
                    // ExtractAssociatedIcon 只给 32x32 那一张；按原尺寸摆放，不拉伸。
                    _picIcon.Image = ico.ToBitmap();
                }
            }
            catch { }

            // ---- 顶栏 ----
            _pnlHeader.BackColor = pal.Header;
            Put(_pnlHeader, 0, 0, 640, 76);
            _picIcon.SizeMode = PictureBoxSizeMode.StretchImage;
            Put(_picIcon, 24, 22, 32, 32);
            _lblTitle.Text = "MDEditor";
            _lblTitle.Font = Ui.FontOf(15f, FontStyle.Bold);
            _lblTitle.ForeColor = pal.HeaderText;
            _lblTitle.BackColor = Color.Transparent;
            Put(_lblTitle, 72, 16, 320, 28);
            _lblSub.Text = "v" + Setup.Version + " 安装程序";
            _lblSub.Font = Ui.FontOf(9f, FontStyle.Regular);
            _lblSub.ForeColor = pal.HeaderSub;
            _lblSub.BackColor = Color.Transparent;
            Put(_lblSub, 74, 44, 320, 20);
            _pnlHeader.Controls.Add(_picIcon);
            _pnlHeader.Controls.Add(_lblTitle);
            _pnlHeader.Controls.Add(_lblSub);

            // ---- 状态条 ----
            bool wv2 = Setup.WebView2Present();
            _pnlStatus.BackColor = pal.Surface;
            Put(_pnlStatus, 20, 92, 600, 38);
            _pnlDot.BackColor = wv2 ? pal.Ok : pal.Warn;
            Put(_pnlDot, 0, 0, 4, 38);
            _lblStatus.Text = wv2
                ? "已检测到 WebView2 运行时，内嵌窗口可用（系统内核，不捆绑）"
                : "未检测到 WebView2 运行时，将以浏览器模式打开（其余功能不受影响）";
            _lblStatus.ForeColor = pal.TextDim;
            _lblStatus.TextAlign = ContentAlignment.MiddleLeft;
            Put(_lblStatus, 16, 0, 570, 38);
            _pnlStatus.Controls.Add(_pnlDot);
            _pnlStatus.Controls.Add(_lblStatus);

            // ---- 安装目录 ----
            _lblDir.Text = "安装目录：";
            _lblDir.ForeColor = pal.Text;
            Put(_lblDir, 20, 144, 76, 22);
            _txtDir.Text = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "MDEditor");
            _txtDir.Font = Ui.FontOf(9f, FontStyle.Regular);
            _txtDir.BorderStyle = BorderStyle.FixedSingle;
            _txtDir.BackColor = pal.Surface;
            _txtDir.ForeColor = pal.Text;
            // 默认不选中整段：全选态是深蓝底白字，看上去像被误触。
            // TextBox 拿到焦点会自动全选，.NET Framework 没有 AutoSelectAll 属性，
            // 只能在句柄创建后主动把选区收到末尾。
            _txtDir.HandleCreated += (s, e) =>
            {
                _txtDir.SelectionLength = 0;
                _txtDir.SelectionStart = _txtDir.TextLength;
            };
            Put(_txtDir, 100, 141, 420, 26);
            _btnBrowse.Text = "浏览...";
            StyleSecondary(_btnBrowse, pal);
            Put(_btnBrowse, 528, 140, 92, 28);
            _btnBrowse.Click += (s, e) =>
            {
                using (var d = new FolderBrowserDialog { Description = "选择 MDEditor 安装目录", SelectedPath = _txtDir.Text })
                    if (d.ShowDialog(this) == DialogResult.OK) _txtDir.Text = d.SelectedPath;
            };

            // ---- 主按钮 + 进度 ----
            _btnInstall.Text = "开始安装";
            StylePrimary(_btnInstall, pal);
            Put(_btnInstall, 20, 182, 120, 32);
            _btnInstall.Click += (s, e) => StartInstall();
            _prog.Style = ProgressBarStyle.Continuous;
            Put(_prog, 152, 187, 468, 22);

            // ---- 日志区 ----
            _grpLog.Text = "安装日志";
            _grpLog.ForeColor = pal.TextDim;
            _grpLog.BackColor = pal.Canvas;
            Put(_grpLog, 20, 226, 600, 250);
            _txtLog.Multiline = true;
            _txtLog.ReadOnly = true;
            _txtLog.ScrollBars = ScrollBars.Vertical;
            _txtLog.BackColor = pal.Surface;
            _txtLog.ForeColor = pal.Text;
            // GroupBox 自带边框，内部文本框不再画一层，避免双框嵌套。
            _txtLog.BorderStyle = BorderStyle.None;
            _txtLog.Font = Ui.MonoFontOf(9f);
            Put(_txtLog, 10, 22, 584, 216);
            _grpLog.Controls.Add(_txtLog);

            // ---- 底部操作 ----
            _btnRun.Text = "立即运行";
            _btnRun.Enabled = false;
            StyleSecondary(_btnRun, pal);
            Put(_btnRun, 372, 492, 112, 32);
            _btnRun.Click += (s, e) =>
            {
                var pyw = Path.Combine(_target, "python", "pythonw.exe");
                var entry = Path.Combine(_target, "md_launch.pyw");
                Process.Start(new ProcessStartInfo(pyw, "\"" + entry + "\"") { WorkingDirectory = _target, UseShellExecute = false });
                Close();
            };
            _btnExit.Text = "退出";
            StyleSecondary(_btnExit, pal);
            Put(_btnExit, 494, 492, 126, 32);
            _btnExit.Click += (s, e) => Close();

            Controls.AddRange(new Control[] {
                _pnlHeader, _pnlStatus, _lblDir, _txtDir, _btnBrowse,
                _btnInstall, _prog, _grpLog, _btnRun, _btnExit
            });
            AcceptButton = _btnInstall;

            ApplyScale(ScaleFactor());
        }

        static void StylePrimary(Button b, Palette pal)
        {
            b.FlatStyle = FlatStyle.Flat;
            b.FlatAppearance.BorderSize = 0;
            b.UseVisualStyleBackColor = false;
            b.BackColor = pal.Accent;
            b.ForeColor = pal.AccentText;
            b.Font = Ui.FontOf(9.5f, FontStyle.Bold);
            b.Cursor = Cursors.Hand;
        }

        static void StyleSecondary(Button b, Palette pal)
        {
            b.FlatStyle = FlatStyle.Flat;
            b.FlatAppearance.BorderSize = 1;
            b.FlatAppearance.BorderColor = pal.Border;
            b.UseVisualStyleBackColor = false;
            b.BackColor = pal.Surface;
            b.ForeColor = pal.Text;
            b.Cursor = Cursors.Hand;
        }

        // 记录设计稿坐标（相对父容器），缩放时按实际 DPI 重新换算。
        void Put(Control c, int x, int y, int w, int h)
        {
            _design[c] = new Rectangle(x, y, w, h);
            c.Location = new Point(x, y);
            c.Size = new Size(w, h);
        }

        static float ScaleFactor()
        {
            try
            {
                uint dpi = GetDpiForSystem();
                if (dpi >= 96) return dpi / 96f;
            }
            catch { }
            return 1f;
        }

        void ApplyScale(float k)
        {
            _k = k;
            foreach (var kv in _design)
            {
                var r = kv.Value;
                kv.Key.Location = new Point((int)Math.Round(r.X * k), (int)Math.Round(r.Y * k));
                kv.Key.Size = new Size((int)Math.Round(r.Width * k), (int)Math.Round(r.Height * k));
            }
            ClientSize = new Size((int)Math.Round(640 * k), (int)Math.Round(540 * k));
        }

        protected override void OnLoad(EventArgs e)
        {
            base.OnLoad(e);
            try
            {
                uint dpi = GetDpiForWindow(Handle);
                if (dpi >= 96) ApplyScale(dpi / 96f);
            }
            catch { }
            ApplyTitleBarStyle();
        }

        // 标题栏跟随顶栏配色：Windows 默认标题栏是系统强调色（蓝），跟深色顶栏
        // 并排会割裂。DWMWA_CAPTION_COLOR 属 Win11 22H2+，老系统上设置失败就
        // 保持系统默认，不影响其余部分。
        void ApplyTitleBarStyle()
        {
            var pal = Ui.Current;
            try
            {
                int dark = pal.Dark ? 1 : 0;
                uint darkU = (uint)dark;
                DwmSetWindowAttribute(Handle, 20, ref darkU, 4);  // 标题栏跟随深色
                DwmSetWindowAttribute(Handle, 19, ref darkU, 4);  // Win10 2004 以前
            }
            catch { }
            try
            {
                // COLORREF 打包值是 0x00BBGGRR（红在最低字节）。
                uint cap = ColorRef(pal.Header);
                uint txt = ColorRef(pal.HeaderText);
                DwmSetWindowAttribute(Handle, 35, ref cap, 4);   // DWMWA_CAPTION_COLOR
                DwmSetWindowAttribute(Handle, 36, ref txt, 4);   // DWMWA_TEXT_COLOR
            }
            catch { }
        }

        static uint ColorRef(Color c)
        {
            return (uint)(c.B << 16 | c.G << 8 | c.R);
        }

        protected override void WndProc(ref Message m)
        {
            if (m.Msg == WM_DPICHANGED)
            {
                int dpi = (int)(m.WParam.ToInt64() & 0xFFFF);
                if (dpi >= 96)
                {
                    ApplyScale(dpi / 96f);
                    var r = (RECT)Marshal.PtrToStructure(m.LParam, typeof(RECT));
                    SetWindowPos(Handle, IntPtr.Zero, r.Left, r.Top,
                                 r.Right - r.Left, r.Bottom - r.Top, 0x0004 /*SWP_NOZORDER*/);
                }
                return;
            }
            base.WndProc(ref m);
        }

        void Log(string msg)
        {
            if (_txtLog.InvokeRequired) { _txtLog.BeginInvoke((Action)(() => Log(msg))); return; }
            _txtLog.AppendText(msg + Environment.NewLine);
        }

        void StartInstall()
        {
            var target = _txtDir.Text.Trim();
            if (target.Length == 0) { MessageBox.Show("请先选择安装目录。"); return; }
            if (string.Equals(Path.GetFullPath(target), Path.GetFullPath(Application.StartupPath), StringComparison.OrdinalIgnoreCase))
            { MessageBox.Show("安装目录不能与安装包自身所在目录相同。"); return; }
            _btnInstall.Enabled = false; _btnBrowse.Enabled = false; _txtDir.Enabled = false;
            _prog.Value = 0;
            Setup.Install(target,
                log => Log(log),
                pct => { if (_prog.InvokeRequired) _prog.BeginInvoke((Action)(() => _prog.Value = pct)); else _prog.Value = pct; },
                () =>
                {
                    if (_prog.InvokeRequired) _prog.BeginInvoke((Action)(() => _prog.Value = _prog.Maximum));
                    else _prog.Value = _prog.Maximum;
                    _target = target;
                    _btnRun.Enabled = true;
                    _btnInstall.Enabled = true; _btnBrowse.Enabled = true; _txtDir.Enabled = true;
                },
                err =>
                {
                    Log("[错误] " + err);
                    MessageBox.Show("安装失败：" + err);
                    _btnInstall.Enabled = true; _btnBrowse.Enabled = true; _txtDir.Enabled = true;
                });
        }
    }
}
