AC_PREREQ(2.65)

AC_INIT([python-toolbox2],[0.9.0~dev])

AM_INIT_AUTOMAKE([foreign])

AM_PATH_PYTHON
AC_PROG_SED
AC_PATH_PROG(TXT2TAGS, txt2tags)

AC_SUBST([fontspkgdatadir], [\$\(pkgdatadir\)/fonts])

AC_CONFIG_FILES([
    Makefile
    bin/Makefile
    conf/Makefile
    doc/Makefile
    share/Makefile
    share/fonts/Makefile
    toolbox2/Makefile
])

AC_OUTPUT
