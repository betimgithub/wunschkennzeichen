--[[
    Remote Tester
    Xeno kann die Aufrufe des Spiels nicht mitlesen, deshalb testen wir
    selbst: Das Fenster feuert das zentrale RemoteEvent des Spiels mit
    verschiedenen Aktionsnamen. Öffnet sich das Ei, haben wir den richtigen.

    Erst NEBEN dem Ei testen, dann weit weg (prüft, ob Fernöffnen geht).
]]

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local remote = ReplicatedStorage:WaitForChild("Shared"):WaitForChild("Framework")
    :WaitForChild("Network"):WaitForChild("Remote"):WaitForChild("RemoteEvent")

-- Vermutete Aufrufe (Aktion, Argumente...). Jeder Eintrag wird ein Knopf.
local PRESETS = {
    { "HatchEgg", "Creaking Egg", 1 },
    { "HatchEgg", "Creaking Egg" },
    { "OpenEgg", "Creaking Egg", 1 },
    { "BuyEgg", "Creaking Egg", 1 },
    { "ClaimChest", "Halloween Chest" },
    { "ClaimChest", "Halloween Chest", true },
    { "OpenChest", "Halloween Chest" },
}

------------------------------------------------------------------------

local parent
if typeof(gethui) == "function" then pcall(function() parent = gethui() end) end
if not parent then pcall(function() parent = game:GetService("CoreGui") end) end

local old = parent and parent:FindFirstChild("RemoteTesterGui")
if old then old:Destroy() end

local screen = Instance.new("ScreenGui")
screen.Name = "RemoteTesterGui"
screen.ResetOnSpawn = false
screen.DisplayOrder = 1000
if not (parent and pcall(function() screen.Parent = parent end) and screen.Parent) then
    screen.Parent = Players.LocalPlayer:WaitForChild("PlayerGui")
end

local frame = Instance.new("Frame")
frame.Size = UDim2.fromOffset(300, 120 + #PRESETS * 30)
frame.Position = UDim2.new(1, -320, 0.2, 0)
frame.BackgroundColor3 = Color3.fromRGB(25, 25, 30)
frame.BorderSizePixel = 0
frame.Active = true
frame.Draggable = true
frame.Parent = screen
Instance.new("UICorner", frame).CornerRadius = UDim.new(0, 8)

local function label(text, y, size, color)
    local l = Instance.new("TextLabel")
    l.Size = UDim2.new(1, -20, 0, 20)
    l.Position = UDim2.fromOffset(10, y)
    l.BackgroundTransparency = 1
    l.TextXAlignment = Enum.TextXAlignment.Left
    l.Font = Enum.Font.GothamBold
    l.TextSize = size
    l.TextColor3 = color
    l.TextWrapped = true
    l.Text = text
    l.Parent = frame
    return l
end

label("Remote Tester – klicken & schauen ob Ei aufgeht", 6, 13, Color3.fromRGB(255, 160, 40))
local status = label("Bereit", 26, 12, Color3.fromRGB(200, 200, 210))

local function describe(args)
    local parts = {}
    for i, v in ipairs(args) do
        parts[i] = type(v) == "string" and string.format("%q", v) or tostring(v)
    end
    return table.concat(parts, ", ")
end

local function fire(args)
    local ok, err = pcall(function() remote:FireServer(table.unpack(args)) end)
    status.Text = ok and ("Gesendet: " .. describe(args)) or ("Fehler: " .. tostring(err))
    print("[RemoteTester]", status.Text)
end

local function makeButton(text, y, onClick)
    local b = Instance.new("TextButton")
    b.Size = UDim2.new(1, -20, 0, 26)
    b.Position = UDim2.fromOffset(10, y)
    b.BackgroundColor3 = Color3.fromRGB(60, 60, 80)
    b.TextColor3 = Color3.new(1, 1, 1)
    b.Font = Enum.Font.Code
    b.TextSize = 12
    b.Text = text
    b.Parent = frame
    Instance.new("UICorner", b).CornerRadius = UDim.new(0, 6)
    b.MouseButton1Click:Connect(onClick)
    return b
end

local y = 50
for _, args in ipairs(PRESETS) do
    makeButton(describe(args), y, function() fire(args) end)
    y += 30
end

-- Eigener Aufruf: Argumente mit Komma trennen, z. B.  HatchEgg, Creaking Egg, 3
local input = Instance.new("TextBox")
input.Size = UDim2.new(1, -90, 0, 26)
input.Position = UDim2.fromOffset(10, y + 6)
input.BackgroundColor3 = Color3.fromRGB(15, 15, 18)
input.TextColor3 = Color3.new(1, 1, 1)
input.PlaceholderText = "Eigene: Aktion, Arg1, Arg2"
input.Font = Enum.Font.Code
input.TextSize = 12
input.ClearTextOnFocus = false
input.Text = ""
input.Parent = frame
Instance.new("UICorner", input).CornerRadius = UDim.new(0, 6)

local send = Instance.new("TextButton")
send.Size = UDim2.fromOffset(66, 26)
send.Position = UDim2.new(1, -76, 0, y + 6)
send.BackgroundColor3 = Color3.fromRGB(46, 120, 200)
send.TextColor3 = Color3.new(1, 1, 1)
send.Font = Enum.Font.GothamBold
send.TextSize = 12
send.Text = "Senden"
send.Parent = frame
Instance.new("UICorner", send).CornerRadius = UDim.new(0, 6)

send.MouseButton1Click:Connect(function()
    local args = {}
    for part in string.gmatch(input.Text, "[^,]+") do
        part = part:match("^%s*(.-)%s*$")
        if part == "true" then
            table.insert(args, true)
        elseif part == "false" then
            table.insert(args, false)
        else
            table.insert(args, tonumber(part) or part)
        end
    end
    if #args > 0 then fire(args) end
end)

local close = makeButton("Schließen", y + 38, function() screen:Destroy() end)
close.BackgroundColor3 = Color3.fromRGB(170, 50, 50)
close.Font = Enum.Font.GothamBold
