*DOMAIN
webtob1

*NODE
APCS1	WEBTOBDIR="/home/jeus6/webtob", 
		SHMKEY = 54000,
		DOCROOT="/home/jeus6/CSCall/webdocs",
		PORT = "80", 
		HTH = 1,
		#Group = "nobody",
		#User = "nobody",
		NODENAME = "$(NODENAME)",
		ERRORDOCUMENT = "503",
		#Options="IgnoreExpect100Continue",
		JSVPORT = 9900,
		IPCPERM = 0777,
		#ServiceOrder = "ext,uri",
		ServiceOrder = "uri,ext",
		LOGGING = "log1",
		ERRORLOG = "log2",
		SYSLOG = "syslog",
		LimitRequestBody=100000000

*VHOST
vhost1		DOCROOT="/home/jeus6/CSCall/webdocs",
		HOSTNAME = "cal.lotteins.co.kr",
		HOSTALIAS = "20.151.5.61,20.151.5.65",
		IndexName = "index.html",
		PORT = "80",
		ServiceOrder = "uri,ext",
		LOGGING = "log3",
		ERRORLOG = "log4"

vhost1_ssl	DOCROOT="/home/jeus6/CSCall/webdocs",
		HOSTNAME = "cal.lotteins.co.kr",
		HOSTALIAS = "20.151.5.61,20.151.5.65",
		IndexName = "index.html",
		PORT = "443",
		ServiceOrder = "uri,ext",
		LOGGING = "log5",
		ERRORLOG = "log6",
		SSLFLAG = Y,
		SSLName = "ssl_lotteins",
		Method = "GET, POST, HEAD, -OPTIONS"

*SSL
ssl_lotteins	CertificateFile      = "/home/jeus6/webtob/ssl/Wildcard.lotteins.co.kr.crt",
		CertificateKeyFile   = "/home/jeus6/webtob/ssl/Wildcard.lotteins.co.kr.key",
		CACertificateFile    = "/home/jeus6/webtob/ssl/GLOBALSIGN_ROOT_CA.crt",
		CertificateChainFile = "/home/jeus6/webtob/ssl/GLOBALSIGN_CA__SHA256__G.crt",
		Protocols            = "-SSLv2,-SSLv3",
		RequiredCiphers      = "HIGH:MEDIUM:!SSLv2:!PSK:!SRP:!ADH:!AECDH:!EXP:!RC4:!IDEA:3DES:!DH"

*SVRGROUP
htmlg		SVRTYPE = HTML
jsvg1		SVRTYPE = JSV
jsvg2		SVRTYPE = JSV, VhostName = "vhost1,vhost1_ssl"

*SERVER
html		SVGNAME = htmlg, MinProc = 20, MaxProc = 100
CSCall		SVGNAME = jsvg2, MinProc = 150, MaxProc = 400
svr_nui		SVGNAME = jsvg2, MinProc = 150, MaxProc = 400
svr_sus		SVGNAME = jsvg2, MinProc = 10, MaxProc = 20
svr_lmu		SVGNAME = jsvg2, MinProc = 10, MaxProc = 20

*URI
uri_nui_static  Match ="regexp", Uri = "^/ncrmwebroot.*[.](htm|html|gif|jpg|css|js)$", Svrtype = HTML, SvrName = html
uri_nui		Uri = "/ncrmwebroot", Svrtype = JSV, SvrName = svr_nui, VhostName="vhost1,vhost1_ssl"
uri_sus		Uri = "/sus", Svrtype = JSV, SvrName = svr_sus
uri_lmu		Uri = "/lmu", Svrtype = JSV, SvrName = svr_lmu
uri1		Uri = "/", Svrtype = JSV, GoToExt=Y

*ALIAS
#alias1		URI = "/cgi-bin/", RealPath = "/home/jeus6/webtob/cgi-bin/"
alias2		URI = "/ncrmwebroot", RealPath = "/home/jeus6/CSCall/webdocs/CAL/ncrmwebroot"

*LOGGING
syslog		Format = "SYSLOG", FileName = "/apcs1data/webtob/log/system.log_%M%%D%%Y%",
			Option = "sync"
log1		Format = "DEFAULT", FileName = "/apcs1data/webtob/log/access.log_%M%%D%%Y%", 
			Option = "sync,env=!Image"
log2		Format = "ERROR", FileName = "/apcs1data/webtob/log/error.log_%M%%D%%Y%", 
			Option = "sync"
log3		Format = "DEFAULT", FileName = "/apcs1data/webtob/log/access_vhost1.log_%M%%D%%Y%", 
			Option = "sync,env=!Image"
log4		Format = "ERROR", FileName = "/apcs1data/webtob/log/error_vhost1.log_%M%%D%%Y%", 
			Option = "sync"
log5		Format = "DEFAULT", FileName = "/apcs1data/webtob/log/access_vhostssl.log_%M%%D%%Y%", 
			Option = "sync,env=!Image"
log6		Format = "ERROR", FileName = "/apcs1data/webtob/log/error_vhostssl.log_%M%%D%%Y%", 
			Option = "sync"

*ERRORDOCUMENT
503		status = 503,
		url = "/503.html"

*EXT
htm		MimeType = "text/html", SvrType = HTML
shtml		MimeType = "text/html", SvrType = HTML
html		MimeType = "text/html", SvrType = HTML
gif		MimeType = "image/gif", SvrType = HTML
jpg		MimeType = "image/jpeg", SvrType = HTML
css		MimeType = "text/css", SvrType = HTML
js		MimeType = "application/x-javascript", SvrType = HTML
