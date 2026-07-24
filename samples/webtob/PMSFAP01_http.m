*DOMAIN
webtob1

*NODE
PMSFWB01	WEBTOBDIR="/app/webtob", 
		SHMKEY = 54000,
		DOCROOT="/app/webtob/docs",
		PORT = "8081", 
		HTH = 1,
		#Group = "nobody",
		#User = "nobody",
		NODENAME = "$(NODENAME)",
		#Options="IgnoreExpect100Continue",
		JSVPORT = 9900,
                UpperDirRestrict = Y,
                ERRORDOCUMENT = "400,401,403,404,405,406,503",
	        Options="ExcludeAllowHeaderOnError",
	        METHOD = "GET, POST, HEAD, -OPTIONS",
                IPCPERM = 0777,
		LOGPERM = 0640,
		LOGGING = "log1",
		ERRORLOG = "log2",
		SYSLOG = "syslog",
		LimitRequestBody=1000000000

*HTH_THREAD
hth_worker
                SendfileThreads = 4,
                AccessLogThread = Y,
                #ReadBufSize=1048576, #1M
                #HtmlsCompression="text/html",
                #SendfileThreshold=32768,
                WorkerThreads=8

	
*VHOST
##### PROD #####
v_tea	        DOCROOT="/app/webtob/docs",
                HOSTNAME = "tea.lotteins.co.kr",
                HOSTALIAS = "20.151.10.94",
                PORT = "7080",
		ServiceOrder = "uri,ext",
		ERRORDOCUMENT = "400,401,403,404,405,406,503",
		METHOD = "GET, POST, HEAD, -OPTIONS",
		SSLFLAG = Y,
		SSLNAME = ssl_lotteins,
                LOGGING = "acc_tea",
		ERRORLOG = "err_tea"

v_oze           DOCROOT="/app/webtob/docs",
                HOSTNAME = "oze.lotteins.co.kr",
                HOSTALIAS = "20.151.10.94",
                PORT = "443",
                ServiceOrder = "uri,ext",
                ERRORDOCUMENT = "400,401,403,404,405,406,503",
                METHOD = "GET, POST, HEAD, -OPTIONS",
		SSLFLAG = Y,
		SSLNAME = ssl_lotteins,
                LOGGING = "acc_oze",
                ERRORLOG = "err_oze"

v_sdv           DOCROOT="/app/webtob/docs",
                HOSTNAME = "sdv.lotteins.co.kr",
                HOSTALIAS = "20.151.10.94",
                PORT = "443",
                ServiceOrder = "uri,ext",
                ERRORDOCUMENT = "400,401,403,404,405,406,503",
                METHOD = "GET, POST, HEAD, -OPTIONS",
		SSLFLAG = Y,
		SSLNAME = ssl_lotteins,
                LOGGING = "acc_sdv",
                ERRORLOG = "err_sdv"

v_cnd           DOCROOT="/deploy/msfweb/cnd",
                HOSTNAME = "cnd.lotteins.co.kr",
                HOSTALIAS = "20.151.10.94",
                PORT = "443",
                ServiceOrder = "ext,uri",
                ERRORDOCUMENT = "400,401,403,404,405,406,503",
                METHOD = "GET, POST, HEAD, -OPTIONS",
		SSLFLAG = Y,
		SSLNAME = ssl_lotteins,
		URLRewrite = Y,
		URLRewriteConfig = "/app/webtob/config/rewrite.conf",
                LOGGING = "acc_cnd",
                ERRORLOG = "err_cnd"

v_plr           DOCROOT="/deploy/msfweb/plr",
                HOSTNAME = "plr.lotteins.co.kr",
                HOSTALIAS = "20.151.10.94",
                PORT = "443",
                ServiceOrder = "ext,uri",
                ERRORDOCUMENT = "400,401,403,404,405,406,503",
                METHOD = "GET, POST, HEAD, -OPTIONS",
		SSLFLAG = Y,
		SSLNAME = ssl_lotteins,
		URLRewrite = Y,
		URLRewriteConfig = "/app/webtob/config/rewrite.conf",
                LOGGING = "acc_plr",
                ERRORLOG = "err_plr"

v_ntc           DOCROOT="/deploy/msfweb/ntc",
                HOSTNAME = "ntc.lotteins.co.kr",
                HOSTALIAS = "20.151.10.94",
                PORT = "443",
                ServiceOrder = "ext,uri",
                ERRORDOCUMENT = "400,401,403,404,405,406,503",
                METHOD = "GET, POST, HEAD, -OPTIONS",
		SSLFLAG = Y,
		SSLNAME = ssl_lotteins,
		URLRewrite = Y,
		URLRewriteConfig = "/app/webtob/config/rewrite.conf",
                LOGGING = "acc_ntc",
                ERRORLOG = "err_ntc"

v_wavy          DOCROOT="/deploy/msfweb/wavy",
                HOSTNAME = "wavy.lotteins.co.kr",
                HOSTALIAS = "20.151.10.94,m.wavy.lotteins.co.kr,wonder.lotteins.co.kr,m.wonder.lotteins.co.kr",
                PORT = "443",
                ServiceOrder = "ext,uri",
                ERRORDOCUMENT = "400,401,403,404,405,406,503",
                METHOD = "GET, POST, HEAD, -OPTIONS",
		SSLFLAG = Y,
		SSLNAME = ssl_lotteins,
                LOGGING = "acc_wavy",
                ERRORLOG = "err_wavy"


*SVRGROUP
htmlg	        SVRTYPE = HTML

##### PROD #####
g_tea	        SVRTYPE = JSV, VhostName = "v_tea"
g_oze           SVRTYPE = JSV, VhostName = "v_oze"
g_sdv           SVRTYPE = JSV, VhostName = "v_sdv"
g_cnd           SVRTYPE = JSV, VhostName = "v_cnd"
g_plr           SVRTYPE = JSV, VhostName = "v_plr"
g_ntc           SVRTYPE = JSV, VhostName = "v_ntc"

*SERVER
##### PROD #####
tea             SVGNAME = g_tea, MinProc = 100, MaxProc = 100, RequestLevelPing = Y, SvrChkTime = 60#, SessionIdCookieKey = "JSESSIONID"
oze             SVGNAME = g_oze, MinProc = 200, MaxProc = 200, RequestLevelPing = Y, SvrChkTime = 60#, SessionIdCookieKey = "JSESSIONID"
sdv             SVGNAME = g_sdv, MinProc = 100, MaxProc = 100, RequestLevelPing = Y, SvrChkTime = 60#, SessionIdCookieKey = "JSESSIONID"
cnd             SVGNAME = g_cnd, MinProc = 600, MaxProc = 600, RequestLevelPing = Y, SvrChkTime = 60#, SessionIdCookieKey = "JSESSIONID"
plr             SVGNAME = g_plr, MinProc = 600, MaxProc = 600, RequestLevelPing = Y, SvrChkTime = 60#, SessionIdCookieKey = "JSESSIONID"
ntc             SVGNAME = g_ntc, MinProc = 100, MaxProc = 100, RequestLevelPing = Y, SvrChkTime = 60#, SessionIdCookieKey = "JSESSIONID"

*URI
##### PROD #####
u_tea	        Uri = "/",   Svrtype = JSV, GotoEXT = N, VhostName = "v_tea",svrname = "tea"
u_oze           Uri = "/",   Svrtype = JSV, GotoEXT = N, VhostName = "v_oze",svrname = "oze"
u_sdv           Uri = "/",   Svrtype = JSV, GotoEXT = N, VhostName = "v_sdv",svrname = "sdv"
u_cnd           Uri = "/",   Svrtype = JSV, GotoEXT = Y, VhostName = "v_cnd",svrname = "cnd"
u_plr           Uri = "/",   Svrtype = JSV, GotoEXT = Y, VhostName = "v_plr",svrname = "plr"
u_ntc           Uri = "/",   Svrtype = JSV, GotoEXT = Y, VhostName = "v_ntc",svrname = "ntc"

*SSL
ssl_lotteins    CertificateFile      = "/app/webtob/ssl/lotteins/Wildcard.lotteins.co.kr.crt",
                CertificateKeyFile   = "/app/webtob/ssl/lotteins/Wildcard.lotteins.co.kr.key",
                CACertificateFile    = "/app/webtob/ssl/lotteins/GLOBALSIGN_ROOT_CA.crt",
                CertificateChainFile = "/app/webtob/ssl/lotteins/GLOBALSIGN_ORGANIZATION_VALIDATION_CA__SHA256__G.crt",
                Protocols            = "-SSLv2,-SSLv3,-TLSv1,-TLSv1.1",
                RequiredCiphers      = "ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-RSA-AES128-SHA:ECDHE-RSA-AES256-SHA:ECDHE-RSA-AES128-SHA256:ECDHE-RSA-AES256-SHA384"

*ERRORDOCUMENT
400             status = 400, url = "/error.html"
401             status = 401, url = "/error.html"
402             status = 402, url = "/error.html"
403             status = 403, url = "/error.html"
404             status = 404, url = "/error.html"
405             status = 405, url = "/error.html"
406             status = 406, url = "/error.html"
503             status = 503, url = "/error.html"

*ALIAS
#alias1	        URI = "/cgi-bin/", RealPath = "/app/webtob/cgi-bin/"

*LOGGING
syslog	        Format = "SYSLOG",  FileName = "/log/webtob/system.log_%M%%D%%Y%", Option = "sync"
log1	        Format = "%h %t \"%r\" %s %b \"%{content-length}i\" %D \"%{Referer}i\" \"%{User-Agent}i\" \"%{X-Forwarded-For}i\"", FileName = "/log/webtob/access.log_%M%%D%%Y%", Option = "sync"
log2		Format = "ERROR",   FileName = "/log/webtob/error.log_%M%%D%%Y%", Option = "sync"

##### PROD #####
acc_tea 	Format = "%h %t \"%r\" %s %b \"%{content-length}i\" %D \"%{Referer}i\" \"%{User-Agent}i\" \"%{X-Forwarded-For}i\"", FileName = "/log/webtob/tea/access_%Y%%M%%D%.log", Option = "sync"
err_tea 	Format = "ERROR",   FileName = "/log/webtob/tea/error_%Y%%M%%D%.log", Option = "sync"
acc_oze         Format = "%h %t \"%r\" %s %b \"%{content-length}i\" %D \"%{Referer}i\" \"%{User-Agent}i\" \"%{X-Forwarded-For}i\"", FileName = "/log/webtob/oze/access_%Y%%M%%D%.log", Option = "sync"
err_oze         Format = "ERROR",   FileName = "/log/webtob/oze/error_%Y%%M%%D%.log", Option = "sync"
acc_sdv         Format = "%h %t \"%r\" %s %b \"%{content-length}i\" %D \"%{Referer}i\" \"%{User-Agent}i\" \"%{X-Forwarded-For}i\"", FileName = "/log/webtob/sdv/access_%Y%%M%%D%.log", Option = "sync"
err_sdv         Format = "ERROR",   FileName = "/log/webtob/sdv/error_%Y%%M%%D%.log", Option = "sync"
acc_cnd         Format = "%h %t \"%r\" %s %b \"%{content-length}i\" %D \"%{Referer}i\" \"%{User-Agent}i\" \"%{X-Forwarded-For}i\"", FileName = "/log/webtob/cnd/access_%Y%%M%%D%.log", Option = "sync"
err_cnd         Format = "ERROR",   FileName = "/log/webtob/cnd/error_%Y%%M%%D%.log", Option = "sync"
acc_plr         Format = "%h %t \"%r\" %s %b \"%{content-length}i\" %D \"%{Referer}i\" \"%{User-Agent}i\" \"%{X-Forwarded-For}i\"", FileName = "/log/webtob/plr/access_%Y%%M%%D%.log", Option = "sync"
err_plr         Format = "ERROR",   FileName = "/log/webtob/plr/error_%Y%%M%%D%.log", Option = "sync"
acc_ntc         Format = "%h %t \"%r\" %s %b \"%{content-length}i\" %D \"%{Referer}i\" \"%{User-Agent}i\" \"%{X-Forwarded-For}i\"", FileName = "/log/webtob/ntc/access_%Y%%M%%D%.log", Option = "sync"
err_ntc         Format = "ERROR",   FileName = "/log/webtob/ntc/error_%Y%%M%%D%.log", Option = "sync"
acc_wavy        Format = "%h %t \"%r\" %s %b \"%{content-length}i\" %D \"%{Referer}i\" \"%{User-Agent}i\" \"%{X-Forwarded-For}i\"", FileName = "/log/webtob/wavy/access_%Y%%M%%D%.log", Option = "sync"
err_wavy        Format = "ERROR",   FileName = "/log/webtob/wavy/error_%Y%%M%%D%.log", Option = "sync"

*EXT
htm             MimeType = "text/html", SvrType = HTML
html            MimeType = "text/html", SvrType = HTML
jsp             MimeType = "application/jsp", SvrType = JSV, Options = "unset"
css             MimeType = "text/css", SvrType = HTML
htc             MimeType = "text/x-component", SvrType = HTML
js              MimeType = "application/x-javascript", SvrType = HTML
txt             MimeType = "text/plain", SvrType = HTML
ico             MimeType = "image/x-icon", SvrType = HTML
gif             MimeType = "image/gif", SvrType = HTML
jpg             MimeType = "image/jpeg", SvrType = HTML
png             MimeType = "image/png", SvrType = HTML
swf             MimeType = "application/x-shockwave-flash", SvrType=HTML
doc             MimeType = "application/msword", SvrType = HTML
hwp             MimeType = "application/x-hwp", SvrType = HTML
pdf             MimeType = "application/pdf", SvrType = HTML
ppt             MimeType = "application/vnd.ms-powerpoint", SvrType = HTML
xls             MimeType = "application/vnd.ms-excel", SvrType = HTML
exe             MimeType = "application/octet-stream", SvrType = HTML
dll             MimeType = "application/x-msdownload", SvrType = HTML
cab             MimeType = "application/x-compressed", SvrType = HTML
ini             MimeType = "application/octet-stream",  SvrType = HTML
ocx             MimeType = "application/x-pe-win32-x86",    SVRTYPE = HTML
asf             MimeType = "video/x-ms-asf", SvrType = HTML
avi             MimeType = "video/x-msvideo", SvrType = HTML
mov             MimeType = "video/quicktime", SvrType = HTML
mpeg            MimeType = "video/mpeg", SvrType = HTML
mpg             MimeType = "video/mpeg", SvrType = HTML
mp4             MimeType = "video/mp4", SvrType = HTML
wma             MimeType = "audio/x-ms-wma", SvrType = HTML
wmv             MimeType = "audio/x-ms-wmv", SvrType = HTML
tar             MimeType = "application/x-tar", SvrType = HTML
zip             MimeType = "application/zip", SvrType = HTML
alz             MimeType = "application/zip", SvrType = HTML
eot             MimeType = "application/vnd.ms-fontobject", SvrType = HTML
otf             MimeType = "application/font-sfnt", SvrType = HTML
ttf             MimeType = "application/font-sfnt", SvrType = HTML
woff            MimeType = "application/font-woff", SvrType = HTML
svg             MimeType = "image/svg+xml", SvrType = HTML
xhtml           MimeType = "application/xhtml+xml", SvrType = HTML
xml             MimeType = "application/xml", SvrType = HTML
docx            MimeType = "application/vnd.openxmlformats-officedocument.wordprocessingml.document", SvrType = HTML
xlsx            MimeType = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", SvrType = HTML
pptx            MimeType = "application/vnd.openxmlformats-officedocument.presentationml.presentation", SvrType = HTML
idf             MimeType = "text/plain", SvrType=HTML
apk             MimeType = "application/vnd.android.package-archive", SvrType = HTML
ipa             MimeType = "application/octet-stream", SvrType = HTML
plist           MimeType = "text/html", SvrType = HTML
