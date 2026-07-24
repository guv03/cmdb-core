*DOMAIN
webtob1

*NODE
PNGSAP01	WEBTOBDIR="/app/webtob", 
		SHMKEY = 54000,
		DOCROOT="/deploy/ngsapp/ngsdevs",
		PORT = "7090", 
		HTH = 4,
		#User = "nobody",
		NODENAME = "$(NODENAME)",
		ERRORDOCUMENT = "400,401,403,404,405,503",
                 SSLFLAG    = Y,
                 SSLName    = "ssl_lotteins",
		ServiceOrder =  "uri,ext",
		#Options="IgnoreExpect100Continue",
		JSVPORT = 9900,
                Timeout = 3600,
		LOGGING = "acc_node",
		ERRORLOG = "err_node",
		SYSLOG = "syslog",
		LimitRequestBody = 209715200

*HTH_THREAD
hth_worker
                  SendfileThreads = 4,
                  AccessLogThread = Y,
                  #ReadBufSize=1048576, #1M
                  #HtmlsCompression="text/html",
                  #SendfileThreshold=32768,
                  WorkerThreads=8

*VHOST
vh_ngs_ssl       DOCROOT    = "/deploy/ngsapp/ngsonline",
                 HOSTNAME   = "ngs.lotteins.co.kr",
		 HOSTALIAS  = "20.151.6.16,20.151.6.20,hne.lotteins.co.kr",
                 PORT       = "7090",
		 ServiceOrder =  "uri,ext",
                 SSLFLAG    = Y,
                 SSLName    = "ssl_lotteins",
                 ErrorDocument = "400,401,403,404,405,503",
         	 KeepAlive = Y,
         	 KeepAliveTimeout = 120,
     	     	 KeepAliveMax = 0,
                 LOGGING = "acc_ngs",
                 ERRORLOG = "err_ngs"

vh_cid_ssl       DOCROOT    = "/deploy/jeus8",
                 HOSTNAME   = "cid.lotteins.co.kr",
		 HOSTALIAS  = "20.151.6.16,20.151.6.20",
                 PORT       = "7091",
		 ServiceOrder =  "ext,uri",
                 SSLFLAG    = Y,
                 SSLName    = "ssl_lotteins",
                 ErrorDocument = "400,401,403,404,405,503",
                 LOGGING = "acc_cid",
                 ERRORLOG = "err_cid"

vh_bnc_ssl       DOCROOT    = "/deploy/bnc/online",
                 HOSTNAME   = "bnc.lotteins.co.kr",
		 HOSTALIAS  = "20.151.6.16,20.151.6.20",
                 PORT       = "7092",
		 ServiceOrder =  "ext,uri",
                 SSLFLAG    = Y,
                 SSLName    = "ssl_lotteins",
                 ErrorDocument = "400,401,403,404,405,503",
                 LOGGING = "acc_bnc",
                 ERRORLOG = "err_bnc"

vh_inb_ssl       DOCROOT    = "/app/innorule",
                 HOSTNAME   = "inno.lotteins.co.kr",
		 HOSTALIAS  = "20.151.6.16,20.151.6.20",
                 PORT       = "7093",
                 ServiceOrder =  "uri,ext",
                 SSLFLAG    = Y,
                 SSLName    = "ssl_lotteins",
                 ErrorDocument = "400,401,403,404,405,503",
                 KeepAlive = Y,
                 KeepAliveTimeout = 120,
                 KeepAliveMax = 0,
                 LOGGING = "acc_inb",
                 ERRORLOG = "err_inb"

*SSL
ssl_lotteins    CertificateFile      = "/app/webtob/ssl/lotteins/Wildcard.lotteins.co.kr.crt",
                CertificateKeyFile   = "/app/webtob/ssl/lotteins/Wildcard.lotteins.co.kr.key",
                CACertificateFile    = "/app/webtob/ssl/lotteins/GLOBALSIGN_ROOT_CA.crt",
                CertificateChainFile = "/app/webtob/ssl/lotteins/GLOBALSIGN_ORGANIZATION_VALIDATION_CA__SHA256__G.crt",
                Protocols            = "-SSLv2,-SSLv3",
                RequiredCiphers      = "HIGH:MEDIUM:!SSLv2:!PSK:!SRP:!ADH:!AECDH:!EXP:!RC4:!IDEA:3DES:!DH"


*SVRGROUP
htmlg		SVRTYPE = HTML
jsvg_ngs	SVRTYPE = JSV, VHOSTNAME = "vh_ngs_ssl"
jsvg_cid	SVRTYPE = JSV, VHOSTNAME = "vh_cid_ssl"
jsvg_bnc	SVRTYPE = JSV, VHOSTNAME = "vh_bnc_ssl"
jsvg_inb        SVRTYPE = JSV, VHOSTNAME = "vh_inb_ssl"

*SERVER
svr_cont	SVGNAME = jsvg_ngs, MinProc = 800, MaxProc = 800, ASQCount = 1
svr_noncont	SVGNAME = jsvg_ngs, MinProc = 180, MaxProc = 180, ASQCount = 1 
svr_long	SVGNAME = jsvg_ngs, MinProc = 60, MaxProc = 60, ASQCount = 1 
svr_ifs 	SVGNAME = jsvg_ngs, MinProc = 30, MaxProc = 30, ASQCount = 1 
svr_ops		SVGNAME = jsvg_ngs, MinProc = 60, MaxProc = 60, ASQCount = 1 
svr_prorule	SVGNAME = jsvg_ngs, MinProc = 60, MaxProc = 60, ASQCount = 1
svr_lms         SVGNAME = jsvg_ngs, MinProc = 60, MaxProc = 60, ASQCount = 1
svr_cid 	SVGNAME = jsvg_cid, MinProc = 60, MaxProc = 60, ASQCount = 1
svr_bnc 	SVGNAME = jsvg_bnc, MinProc = 60, MaxProc = 60, ASQCount = 1
svr_inb         SVGNAME = jsvg_inb, MinProc = 60, MaxProc = 60, ASQCount = 1

*URI
uri_cont        Uri = "/ONLINE",   Svrtype = JSV, SvrName = "svr_cont", VHOSTNAME = "vh_ngs_ssl", GotoEXT = Y
uri_noncont     Uri = "/ONLINEN",  Svrtype = JSV, SvrName = "svr_noncont", VHOSTNAME = "vh_ngs_ssl", GotoEXT = Y
uri_long        Uri = "/ONLINEL",  Svrtype = JSV, SvrName = "svr_long", VHOSTNAME = "vh_ngs_ssl", GotoEXT = Y
uri_ifs         Uri = "/ONLINEIFS",  Svrtype = JSV, SvrName = "svr_ifs", VHOSTNAME = "vh_ngs_ssl", GotoEXT = Y
uri_ops         Uri = "/honeop",   Svrtype = JSV, SvrName = "svr_ops", VHOSTNAME = "vh_ngs_ssl"
uri_prorule     Uri = "/prorule",Svrtype = JSV, SvrName = "svr_prorule", VHOSTNAME = "vh_ngs_ssl", GotoEXT = Y
uri_lms         Uri = "/service",   Svrtype = JSV, SvrName = "svr_lms", VHOSTNAME = "vh_ngs_ssl"#, GotoEXT = Y
uri_inb         Uri = "/",Svrtype = JSV, SvrName = "svr_inb", VHOSTNAME = "vh_inb_ssl", GotoEXT = Y
uri_cid         Uri = "/",Svrtype = JSV, SvrName = "svr_cid", VHOSTNAME = "vh_cid_ssl"#, GotoEXT = Y
uri_bnc         Uri = "/",Svrtype = JSV, SvrName = "svr_bnc", VHOSTNAME = "vh_bnc_ssl"#, GotoEXT = Y

*ALIAS
alias1          URI = "/bncOnline/", RealPath = "/deploy/bnc/online/"
alias2          URI = "/ONLINE/", RealPath = "/deploy/ngsapp/ngsonline/"
alias3          URI = "/ONLINEL/", RealPath = "/deploy/ngsapp/ngsonline/"
alias4          URI = "/ONLINEN/", RealPath = "/deploy/ngsapp/ngsonline/"
alias8          URI = "/ONLINEIFS/", RealPath = "/deploy/ngsapp/ngsonline_ifs/"
#alias5         URI = "/honeop/resources/", RealPath = "/deploy/hone/honeops/WEB-INF/classes/public-web-resources/"
alias6          URI = "/honexpert/", RealPath = "/deploy/hone/honexpert/"
alias7          URI = "/prorule/", RealPath = "/deploy/prorule/servlet/"

*LOGGING
syslog		Format = "SYSLOG", FileName = "/log/webtob/syslog/system.log_%Y%%M%%D%", Option = "sync"
acc_node	Format = "DEFAULT", FileName = "/log/webtob/node_access.log_%Y%%M%%D%", Option = "sync"
err_node	Format = "ERROR", FileName = "/log/webtob/node_error.log_%Y%%M%%D%", Option = "sync"
acc_ngs		Format = "DEFAULT", FileName = "/log/webtob/ngs_access.log_%Y%%M%%D%", Option = "sync"
err_ngs		Format = "ERROR", FileName = "/log/webtob/ngs_error.log_%Y%%M%%D%", Option = "sync"
acc_cid		Format = "DEFAULT", FileName = "/log/webtob/cid_access.log_%Y%%M%%D%", Option = "sync"
err_cid		Format = "ERROR", FileName = "/log/webtob/cid_error.log_%Y%%M%%D%", Option = "sync"
acc_bnc		Format = "DEFAULT", FileName = "/log/webtob/bnc_access.log_%Y%%M%%D%", Option = "sync"
err_bnc		Format = "ERROR", FileName = "/log/webtob/bnc_error.log_%Y%%M%%D%", Option = "sync"
acc_inb         Format = "DEFAULT", FileName = "/log/webtob/inb_access.log_%Y%%M%%D%", Option = "sync"
err_inb         Format = "ERROR", FileName = "/log/webtob/inb_error.log_%Y%%M%%D%", Option = "sync"

*ERRORDOCUMENT
400             Status = 400, URL = "/error.html"
401             Status = 401, URL = "/error.html"
403             Status = 403, URL = "/error.html"
404             Status = 404, URL = "/error.html"
405             Status = 405, URL = "/error.html"
503             Status = 503, URL = "/error.html"

*EXT
htm             MimeType = "text/html",              SvrType = HTML
html            MimeType = "text/html",              SvrType = HTML
gif             MimeType = "image/gif",              SvrType = HTML
jpg             MimeType = "image/jpeg",             SvrType = HTML
bmp             MimeType = "image/bmp",              SvrType = HTML
swf             MimeType = "image/swf",              SvrType = HTML
png             MimeType = "image/png",              SvrType = HTML
css             MimeType = "text/css",               SvrType = HTML
js              MimeType = "application/javascript", SvrType = HTML
xml             MimeType = "application/xml",        SvrType = HTML
jsp             MimeType = "application/jsp",        SvrType = JSV, Options = "UnSet"
