package main

import (
	"bufio"
	"database/sql"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"sort"
	"strings"
	"sync"
	"time"

	"context"
	_ "github.com/go-sql-driver/mysql"
	"github.com/joho/godotenv"
	"golang.org/x/crypto/ssh"
	"os/signal"
	"os/user"
	"syscall"
)

// ─────────────────────────────────────────────
// Models
// ─────────────────────────────────────────────

type Settings struct {
	UserName     string `json:"user_name"`
	GitBashPath  string `json:"git_bash_path"`
	WorkspaceURL string `json:"workspace_url"`
	PreDeployCmd string `json:"pre_deploy_cmd"`
	GoPrivate    string `json:"go_private"`
}

type Service struct {
	Name       string `json:"name"`
	Dir        string `json:"dir"`
	Branch     string `json:"branch"`
	LastCommit string `json:"last_commit"`
	HasDev     bool   `json:"has_dev"`
	HasStg     bool   `json:"has_stg"`
	DevScript  string `json:"dev_script"`
	StgScript  string `json:"stg_script"`
}

type DeployLog struct {
	UserName    string `json:"user_name"`
	Environment string `json:"environment"`
	Branch      string `json:"branch"`
	CreatedAt   string `json:"created_at"`
	Message     string `json:"message"`
}

// ─────────────────────────────────────────────
// Configuration & Globals
// ─────────────────────────────────────────────

var (
	basePath string
	settings Settings

	// Database Persistence
	globalDB      *sql.DB
	globalCleanup func()
	dbMu          sync.Mutex
)

func init() {
	err := godotenv.Load()
	if err != nil {
		log.Printf("[Init] Warning: .env file not found, using system environment variables")
	} else {
		log.Printf("[Init] Loaded .env file successfully")
	}

	exePath, err := os.Executable()
	if err != nil {
		basePath = "."
	} else {
		basePath = filepath.Dir(exePath)
	}

	// If running with 'go run', use current directory
	if strings.Contains(strings.ToLower(exePath), "go-build") || strings.Contains(strings.ToLower(exePath), "debug") {
		basePath, _ = os.Getwd()
	}
}

func getSettingsPath() string {
	return filepath.Join(basePath, "settings.json")
}

func loadSettings() Settings {
	s := Settings{
		UserName:     "",
		GitBashPath:  `C:\Program Files\Git\bin\bash.exe`,
		WorkspaceURL: filepath.Dir(basePath),
		PreDeployCmd: "",
		GoPrivate:    "gitlab.com/bship1/*",
	}

	f, err := os.Open(getSettingsPath())
	if err == nil {
		defer f.Close()
		_ = json.NewDecoder(f).Decode(&s)
	}
	return s
}

func saveSettings(s Settings) error {
	f, err := os.Create(getSettingsPath())
	if err != nil {
		return err
	}
	defer f.Close()
	encoder := json.NewEncoder(f)
	encoder.SetIndent("", "    ")
	return encoder.Encode(s)
}

// ─────────────────────────────────────────────
// Database & SSH Logic
// ─────────────────────────────────────────────

// getDB provides a persistent database connection
func getDB() (*sql.DB, error) {
	dbMu.Lock()
	defer dbMu.Unlock()

	if globalDB != nil {
		if err := globalDB.Ping(); err == nil {
			return globalDB, nil
		}
		log.Printf("[DB] Connection lost, reconnecting...")
		if globalCleanup != nil {
			globalCleanup()
		}
		globalDB.Close()
		globalDB = nil
	}

	db, cleanup, err := createDBConnection()
	if err != nil {
		return nil, err
	}
	globalDB = db
	globalCleanup = cleanup
	return globalDB, nil
}

func createDBConnection() (*sql.DB, func(), error) {
	dbHost := strings.TrimSpace(os.Getenv("MYSQL_HOST"))
	if dbHost == "" {
		dbHost = "localhost"
	}
	dbUser := strings.TrimSpace(os.Getenv("MYSQL_USER"))
	if dbUser == "" {
		dbUser = "root"
	}
	dbPwd := strings.TrimSpace(os.Getenv("MYSQL_PASSWORD"))
	dbName := strings.TrimSpace(os.Getenv("MYSQL_DB"))
	if dbName == "" {
		dbName = "deploy_logs"
	}
	dbPort := strings.TrimSpace(os.Getenv("MYSQL_PORT"))
	if dbPort == "" {
		dbPort = "3306"
	}

	appEnv := strings.ToLower(strings.TrimSpace(os.Getenv("APP_ENV")))
	if appEnv == "" {
		appEnv = "local"
	}
	useSSH := strings.ToLower(strings.TrimSpace(os.Getenv("USE_SSH"))) == "true" || appEnv == "local"

	log.Printf("[DB] Config: APP_ENV=%s, USE_SSH=%s (effective useSSH=%v)", os.Getenv("APP_ENV"), os.Getenv("USE_SSH"), useSSH)

	var cleanup func() = func() {}

	if useSSH && appEnv == "local" {
		sshHost := strings.TrimSpace(os.Getenv("SSH_HOST"))
		sshPort := strings.TrimSpace(os.Getenv("SSH_PORT"))
		if sshPort == "" {
			sshPort = "22"
		}
		sshUser := strings.TrimSpace(os.Getenv("SSH_USER"))
		sshKey := strings.TrimSpace(os.Getenv("SSH_KEY_PATH"))
		sshPwd := strings.TrimSpace(os.Getenv("SSH_PASSWORD"))

		if sshHost != "" && sshUser != "" {
			log.Printf("[SSH] Connecting to %s:%s as %s...", sshHost, sshPort, sshUser)
			var auth []ssh.AuthMethod
			if sshKey != "" {
				key, err := os.ReadFile(sshKey)
				if err != nil {
					log.Printf("[SSH] Error reading key %s: %v", sshKey, err)
					return nil, cleanup, fmt.Errorf("failed to read SSH key: %v", err)
				}
				signer, err := ssh.ParsePrivateKey(key)
				if err != nil {
					log.Printf("[SSH] Error parsing key %s: %v", sshKey, err)
					return nil, cleanup, fmt.Errorf("failed to parse SSH key: %v", err)
				}
				auth = append(auth, ssh.PublicKeys(signer))
			} else {
				auth = append(auth, ssh.Password(sshPwd))
			}

			sshConfig := &ssh.ClientConfig{
				User:            sshUser,
				Auth:            auth,
				HostKeyCallback: ssh.InsecureIgnoreHostKey(),
				Timeout:         10 * time.Second,
			}

			sshClient, err := ssh.Dial("tcp", net.JoinHostPort(sshHost, sshPort), sshConfig)
			if err != nil {
				log.Printf("[SSH] Dial error: %v", err)
				return nil, cleanup, fmt.Errorf("failed to connect to SSH: %v", err)
			}
			log.Printf("[SSH] Connected successfully")

			localListener, err := net.Listen("tcp", "127.0.0.1:0")
			if err != nil {
				sshClient.Close()
				return nil, cleanup, fmt.Errorf("failed to start local listener for SSH: %v", err)
			}

			localPort := localListener.Addr().(*net.TCPAddr).Port
			log.Printf("[SSH] Local tunnel listener on 127.0.0.1:%d", localPort)

			go func() {
				for {
					localConn, err := localListener.Accept()
					if err != nil {
						return
					}

					log.Printf("[SSH] Tunnel: Accepted local connection, dialing remote %s:%s...", dbHost, dbPort)
					remoteConn, err := sshClient.Dial("tcp", net.JoinHostPort(dbHost, dbPort))
					if err != nil {
						log.Printf("[SSH] Tunnel: Dial remote error: %v", err)
						localConn.Close()
						continue
					}
					log.Printf("[SSH] Tunnel: Connected to remote DB host")

					go func() {
						defer localConn.Close()
						defer remoteConn.Close()
						io.Copy(localConn, remoteConn)
					}()
					go func() {
						defer localConn.Close()
						defer remoteConn.Close()
						io.Copy(remoteConn, localConn)
					}()
				}
			}()

			cleanup = func() {
				log.Printf("[SSH] Closing tunnel and client")
				localListener.Close()
				sshClient.Close()
			}

			dsn := fmt.Sprintf("%s:%s@tcp(127.0.0.1:%d)/%s?parseTime=true", dbUser, dbPwd, localPort, dbName)
			db, err := sql.Open("mysql", dsn)
			return db, cleanup, err
		}
	}

	log.Printf("[DB] Connecting directly to %s:%s...", dbHost, dbPort)
	dsn := fmt.Sprintf("%s:%s@tcp(%s:%s)/%s?parseTime=true", dbUser, dbPwd, dbHost, dbPort, dbName)
	db, err := sql.Open("mysql", dsn)
	return db, cleanup, err
}

func logToDB(userName, serviceName, env, branch, message string) error {
	db, err := getDB()
	if err != nil {
		return err
	}

	// Note: We don't close the global DB here

	_, err = db.Exec(`
		CREATE TABLE IF NOT EXISTS deployments (
			id INT AUTO_INCREMENT PRIMARY KEY,
			user_name VARCHAR(100), service VARCHAR(100),
			environment VARCHAR(50), branch VARCHAR(100),
			message TEXT,
			created_at DATETIME DEFAULT CURRENT_TIMESTAMP
		)
	`)
	if err != nil {
		return err
	}

	_, err = db.Exec(`
		INSERT INTO deployments (user_name, service, environment, branch, message, created_at)
		VALUES (?, ?, ?, ?, ?, ?)
	`, userName, serviceName, env, branch, message, time.Now())

	return err
}

// ─────────────────────────────────────────────
// Service Logic
// ─────────────────────────────────────────────

func getBashPath(s Settings) string {
	if runtime.GOOS == "windows" {
		if s.GitBashPath != "" {
			if _, err := os.Stat(s.GitBashPath); err == nil {
				return s.GitBashPath
			}
		}
		standard := `C:\Program Files\Git\bin\bash.exe`
		if _, err := os.Stat(standard); err == nil {
			return standard
		}
		return "bash"
	}
	if path, err := exec.LookPath("bash"); err == nil {
		return path
	}
	return "bash"
}

func getGitPath(s Settings) string {
	if runtime.GOOS == "windows" {
		if s.GitBashPath != "" {
			// e.g. D:\Apps\Git\bin\bash.exe -> D:\Apps\Git\cmd\git.exe
			gitPath := filepath.Join(filepath.Dir(filepath.Dir(s.GitBashPath)), "cmd", "git.exe")
			if _, err := os.Stat(gitPath); err == nil {
				return gitPath
			}
			// Fallback bin\git.exe
			gitPath = filepath.Join(filepath.Dir(s.GitBashPath), "git.exe")
			if _, err := os.Stat(gitPath); err == nil {
				return gitPath
			}
		}
		// Standard paths
		standards := []string{
			`C:\Program Files\Git\cmd\git.exe`,
			`C:\Program Files\Git\bin\git.exe`,
		}
		for _, c := range standards {
			if _, err := os.Stat(c); err == nil {
				return c
			}
		}
	}
	return "git"
}

func ensureGitInPath(s Settings) {
	if runtime.GOOS != "windows" {
		return
	}

	var pathsToCheck []string
	if s.GitBashPath != "" {
		binDir := filepath.Dir(s.GitBashPath)
		cmdDir := filepath.Join(filepath.Dir(binDir), "cmd")
		pathsToCheck = append(pathsToCheck, binDir, cmdDir)
	}
	// Standard paths
	pathsToCheck = append(pathsToCheck, `C:\Program Files\Git\bin`, `C:\Program Files\Git\cmd`)

	currentPath := os.Getenv("PATH")
	pathParts := filepath.SplitList(currentPath)
	pathMap := make(map[string]bool)
	for _, p := range pathParts {
		pathMap[strings.ToLower(filepath.Clean(p))] = true
	}

	updated := false
	for _, p := range pathsToCheck {
		cleanP := filepath.Clean(p)
		if _, err := os.Stat(cleanP); err == nil {
			if !pathMap[strings.ToLower(cleanP)] {
				currentPath = cleanP + string(os.PathListSeparator) + currentPath
				pathMap[strings.ToLower(cleanP)] = true
				updated = true
			}
		}
	}

	if updated {
		os.Setenv("PATH", currentPath)
		log.Printf("[Env] Updated PATH to ensure Git is available")
	}

	if s.GoPrivate != "" {
		os.Setenv("GOPRIVATE", s.GoPrivate)
		log.Printf("[Env] GOPRIVATE set to: %s", s.GoPrivate)
	}
}

func scanServices(s Settings) []Service {
	workspaceURL := s.WorkspaceURL
	gitPath := getGitPath(s)

	var services []Service
	entries, err := os.ReadDir(workspaceURL)
	if err != nil {
		log.Printf("[Scan] Error reading workspace %s: %v", workspaceURL, err)
		return services
	}

	for _, entry := range entries {
		if !entry.IsDir() || strings.HasPrefix(entry.Name(), ".") {
			continue
		}

		path := filepath.Join(workspaceURL, entry.Name())

		devScript := ""
		stgScript := ""

		candidates := []string{
			filepath.Join(path, "deploy-dev.sh"),
			filepath.Join(path, "scripts", "deploy-dev.sh"),
		}
		for _, c := range candidates {
			if _, err := os.Stat(c); err == nil {
				devScript = c
				break
			}
		}

		candidates = []string{
			filepath.Join(path, "deploy-stg.sh"),
			filepath.Join(path, "scripts", "deploy-stg.sh"),
		}
		for _, c := range candidates {
			if _, err := os.Stat(c); err == nil {
				stgScript = c
				break
			}
		}

		if devScript != "" || stgScript != "" {
			branch := "unknown"
			// Use -c safe.directory=* to avoid ownership issues when running as service
			cmd := exec.Command(gitPath, "-c", "safe.directory=*", "rev-parse", "--abbrev-ref", "HEAD")
			cmd.Dir = path
			if out, err := cmd.CombinedOutput(); err == nil {
				branch = strings.TrimSpace(string(out))
			} else {
				log.Printf("[Scan] Git error (branch) in %s: %v, output: %s", entry.Name(), err, string(out))
			}

			lastCommit := ""
			cmd = exec.Command(gitPath, "-c", "safe.directory=*", "log", "-1", "--pretty=%s")
			cmd.Dir = path
			if out, err := cmd.CombinedOutput(); err == nil {
				lastCommit = strings.TrimSpace(string(out))
			} else {
				log.Printf("[Scan] Git error (log) in %s: %v, output: %s", entry.Name(), err, string(out))
			}

			services = append(services, Service{
				Name:       entry.Name(),
				Dir:        path,
				Branch:     branch,
				LastCommit: lastCommit,
				HasDev:     devScript != "",
				HasStg:     stgScript != "",
				DevScript:  devScript,
				StgScript:  stgScript,
			})
		}
	}

	sort.Slice(services, func(i, j int) bool {
		return services[i].Name < services[j].Name
	})

	return services
}

// ─────────────────────────────────────────────
// HTTP Handlers
// ─────────────────────────────────────────────

func indexHandler(w http.ResponseWriter, r *http.Request) {
	http.ServeFile(w, r, filepath.Join(basePath, "templates", "index.html"))
}

func settingsHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodPost {
		var s Settings
		if err := json.NewDecoder(r.Body).Decode(&s); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		if err := saveSettings(s); err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		ensureGitInPath(s)
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
		return
	}

	s := loadSettings()
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(s)
}

func servicesHandler(w http.ResponseWriter, r *http.Request) {
	s := loadSettings()
	services := scanServices(s)
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(services)
}

func historyHandler(w http.ResponseWriter, r *http.Request) {
	serviceName := r.PathValue("service_name")
	if serviceName == "" {
		http.Error(w, "Service name required", http.StatusBadRequest)
		return
	}

	db, err := getDB()
	if err != nil {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusInternalServerError)
		json.NewEncoder(w).Encode(map[string]string{"error": err.Error()})
		return
	}

	rows, err := db.Query(`
		SELECT user_name, environment, branch, created_at, message 
		FROM deployments 
		WHERE service = ? 
		ORDER BY created_at DESC 
		LIMIT 30
	`, serviceName)
	if err != nil {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusInternalServerError)
		json.NewEncoder(w).Encode(map[string]string{"error": err.Error()})
		return
	}
	defer rows.Close()

	var logs []DeployLog
	for rows.Next() {
		var l DeployLog
		var createdAt time.Time
		if err := rows.Scan(&l.UserName, &l.Environment, &l.Branch, &createdAt, &l.Message); err != nil {
			continue
		}
		l.CreatedAt = createdAt.Add(7 * time.Hour).Format("2006-01-02 15:04:05")
		logs = append(logs, l)
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(logs)
}

func deployHandler(w http.ResponseWriter, r *http.Request) {
	var data struct {
		Service string `json:"service"`
		Env     string `json:"env"`
		Message string `json:"message"`
	}
	if err := json.NewDecoder(r.Body).Decode(&data); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	s := loadSettings()
	services := scanServices(s)

	var svc *Service
	for _, sv := range services {
		if sv.Name == data.Service {
			svc = &sv
			break
		}
	}

	if svc == nil {
		http.Error(w, "Service not found", http.StatusNotFound)
		return
	}

	scriptPath := svc.DevScript
	if data.Env == "Staging" {
		scriptPath = svc.StgScript
	}

	if scriptPath == "" {
		http.Error(w, "Script not found for environment", http.StatusBadRequest)
		return
	}

	// SSE Setup
	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")
	w.Header().Set("Access-Control-Allow-Origin", "*")

	flusher, ok := w.(http.Flusher)
	if !ok {
		http.Error(w, "Streaming unsupported", http.StatusInternalServerError)
		return
	}

	send := func(msg string) {
		fmt.Fprintf(w, "data: %s\n\n", msg)
		flusher.Flush()
	}

	bash := getBashPath(s)
	userName := s.UserName
	if userName == "" {
		userName = "WebUser"
	}
	nowStr := time.Now().Format("2006-01-02 15:04:05")
	finalMsg := fmt.Sprintf("[%s] [%s] [%s] %s", userName, svc.Branch, nowStr, data.Message)

	// Step 1: Pre-deploy
	if s.PreDeployCmd != "" {
		send(fmt.Sprintf("[Pre-deploy] $ %s", s.PreDeployCmd))
		var cmd *exec.Cmd
		if runtime.GOOS == "windows" {
			cmd = exec.Command("cmd.exe", "/c", s.PreDeployCmd)
		} else {
			cmd = exec.Command("sh", "-c", s.PreDeployCmd)
		}
		cmd.Dir = svc.Dir
		h, _ := os.UserHomeDir()
		cmd.Env = append(os.Environ(),
			"GIT_TERMINAL_PROMPT=0",
			"GIT_SSH_COMMAND=ssh -o StrictHostKeyChecking=no",
			"GIT_CONFIG_COUNT=1",
			"GIT_CONFIG_KEY_0=url.git@gitlab.com:.insteadOf",
			"GIT_CONFIG_VALUE_0=https://gitlab.com/",
		)
		if h != "" {
			cmd.Env = append(cmd.Env, "HOME="+h, "USERPROFILE="+h)
		}

		stdout, _ := cmd.StdoutPipe()
		cmd.Stderr = cmd.Stdout

		if err := cmd.Start(); err != nil {
			send(fmt.Sprintf("Failed to start pre-deploy: %v", err))
		} else {
			scanner := bufio.NewScanner(stdout)
			for scanner.Scan() {
				send(scanner.Text())
			}
			if err := cmd.Wait(); err != nil {
				send(fmt.Sprintf("\n[Pre-deploy failed — exit %v. Aborting.]", err))
				send("[EOF]")
				return
			}
		}
	}

	// Step 2: Deploy script
	scriptName := filepath.Base(scriptPath)
	scriptDir := filepath.Dir(scriptPath)
	send(fmt.Sprintf("$ bash %s \"%s\"", scriptName, finalMsg))

	cmd := exec.Command(bash, scriptName, finalMsg)
	cmd.Dir = scriptDir
	h, _ := os.UserHomeDir()
	cmd.Env = append(os.Environ(),
		"GIT_TERMINAL_PROMPT=0",
		"GIT_SSH_COMMAND=ssh -o StrictHostKeyChecking=no",
		"GIT_CONFIG_COUNT=1",
		"GIT_CONFIG_KEY_0=url.git@gitlab.com:.insteadOf",
		"GIT_CONFIG_VALUE_0=https://gitlab.com/",
	)
	if h != "" {
		cmd.Env = append(cmd.Env, "HOME="+h, "USERPROFILE="+h)
	}
	stdout, _ := cmd.StdoutPipe()
	cmd.Stderr = cmd.Stdout

	if err := cmd.Start(); err != nil {
		send(fmt.Sprintf("Failed to start deploy: %v", err))
	} else {
		scanner := bufio.NewScanner(stdout)
		for scanner.Scan() {
			send(scanner.Text())
		}
		if err := cmd.Wait(); err == nil {
			send("\n[Deploy finished successfully ✓]")
			err = logToDB(userName, svc.Name, data.Env, svc.Branch, data.Message)
			if err != nil {
				send(fmt.Sprintf("[MySQL] Error: %v", err))
			} else {
				send("[MySQL] Saved deployment log ✓")
			}
		} else {
			send(fmt.Sprintf("\n[Deploy error — exit %v]", err))
		}
	}

	send("[EOF]")
}

// ─────────────────────────────────────────────
// Main
// ─────────────────────────────────────────────

func main() {
	s := loadSettings()
	ensureGitInPath(s)

	u, _ := user.Current()
	h, _ := os.UserHomeDir()
	log.Printf("[Init] Running as user: %s (UID: %s), Home: %s", u.Username, u.Uid, h)

	// Pre-init DB connection to check config
	go func() {
		if _, err := getDB(); err != nil {
			log.Printf("[Init] DB/SSH Warning: %v", err)
		}
	}()

	defer func() {
		dbMu.Lock()
		if globalDB != nil {
			log.Printf("[Main] Closing global DB connection")
			globalDB.Close()
		}
		if globalCleanup != nil {
			globalCleanup()
		}
		dbMu.Unlock()
	}()

	mux := http.NewServeMux()

	mux.HandleFunc("GET /", indexHandler)
	mux.HandleFunc("GET /api/settings", settingsHandler)
	mux.HandleFunc("POST /api/settings", settingsHandler)
	mux.HandleFunc("GET /api/services", servicesHandler)
	mux.HandleFunc("GET /api/history/{service_name}", historyHandler)
	mux.HandleFunc("POST /api/deploy", deployHandler)

	// Static files
	mux.Handle("GET /static/", http.StripPrefix("/static/", http.FileServer(http.Dir(filepath.Join(basePath, "static")))))
	mux.HandleFunc("GET /favicon.ico", func(w http.ResponseWriter, r *http.Request) {
		http.ServeFile(w, r, filepath.Join(basePath, "static", "favicon.ico"))
	})

	port := os.Getenv("PORT")
	if port == "" {
		port = "5000"
	}

	srv := &http.Server{
		Addr:    ":" + port,
		Handler: mux,
	}

	go func() {
		fmt.Printf("Server starting on http://localhost:%s\n", port)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("listen: %s\n", err)
		}
	}()

	// Wait for interrupt signal to gracefully shutdown the server
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit
	log.Println("[Main] Shutting down server...")

	// Create a context with timeout for the shutdown
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := srv.Shutdown(ctx); err != nil {
		log.Printf("[Main] Server forced to shutdown: %v", err)
	}

	log.Println("[Main] Server exiting")
}
