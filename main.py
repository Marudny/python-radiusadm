import radiuscontrol

rc = radiuscontrol.RadiusControl("/var/run/freeradius/freeradius.sock")
rc.connect()
rc.run_command("help")
