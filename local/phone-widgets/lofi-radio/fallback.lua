local mp = require "mp"
local options = require "mp.options"

local settings = { playlist = "jazz" }
options.read_options(settings, "lofi")
mp.set_property("user-data/lofi-playlist", settings.playlist)

mp.register_event("file-loaded", function()
    local first = mp.get_property("playlist/0/filename", "")
    if mp.get_property_number("playlist-pos", 0) > 0 and first:match("^https?://") then
        mp.set_property_native("user-data/lofi-fallback", true)
        mp.commandv("playlist-remove", "0")
    end
end)
