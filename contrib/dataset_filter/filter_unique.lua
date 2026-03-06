#!/usr/bin/env dnsjit
--local dbg = require 'debugger'
--local pprint = require 'krprint'.pprint

if #arg < 2 then
    print("usage: "..arg[1].." <pcap> [<pcap> ...]")
    return
end



local tlds = {}
for line in io.lines("tlds") do
    tlds[line] = true
end


local dn_limit = 5

local stats = require("stats")
local psl = assert(require "psl".builtin())
local object = require("dnsjit.core.objects")
local input = require("dnsjit.input.pcap")
local layer = require("dnsjit.filter.layer")
local dns = require("dnsjit.core.object.dns").new()
local label = require("dnsjit.core.object.dns.label")

local labels = require("dnsjit.core.object.dns.label").new(127)
local q = require("dnsjit.core.object.dns.q").new()

local unique = {}

local function add_unique(unique, qname, qtype, nlabels)
    if qname == nil or nlabels == nil then
        return
    end
    qname = qname:lower()
    local reg_name = psl:registrable_domain(qname)
    if reg_name == nil then
        reg_name = "."
    else
	-- rough heuristics, does not work with \. escaping, but we don't care
	local _, _, tld = qname:find('([^.]+%.)$')
	if tlds[tld] == nil then
	    -- nonsense not present in the root zone
	    return
	end
    end
--dbg()

    if unique[reg_name] == nil then
        unique[reg_name] = {}
    end
    if unique[reg_name][nlabels] == nil then
        unique[reg_name][nlabels] = {}
    end
    if unique[reg_name][nlabels][qtype] == nil then
        unique[reg_name][nlabels][qtype] = {}
        unique[reg_name][nlabels][qtype]["#count"] = 0
    end
    unique[reg_name]["#queries"] = (unique[reg_name]["#queries"] or 0) + 1
    if unique[reg_name][nlabels][qtype]["#count"] < dn_limit then
        qname = string.lower(qname)
        if unique[reg_name][nlabels][qtype][qname] == nil then
            unique[reg_name][nlabels][qtype][qname] = true
            unique[reg_name][nlabels][qtype]["#count"] = unique[reg_name][nlabels][qtype]["#count"] + 1
            unique[reg_name]["#outputs"] = (unique[reg_name]["#outputs"] or 0) + 1

--print("NEW:", qname, pprint(unique, 'error'))
            return true
        end
    end
--print("OLD:", qname, pprint(unique, 'error'))
    return false
end

local function process_packet(obj)
    dns.obj_prev = obj
    local ret = dns:parse_header()
    if ret == 0 and dns.qr == 0 and dns.qdcount > 0 and dns:parse_q(q, labels, 127) == 0 and q.class == dns.CLASS.IN then
        local qnamestr, _ = label.torfc1035(dns, labels, 127)
        return add_unique(unique, qnamestr, dns.type_tostring(q.type), tonumber(q.labels))
    end
    return false
end

local function dn_counts(unique)
    local counts = {}
    -- extract unique[reg_name][nlabels][qtype]["#count"]
    for reg_name, t2 in pairs(unique) do  -- reg_name
        for nlabels, t3 in pairs(t2) do  -- nlabes
	    if type(t3) == 'table' then
		    for qtype, t4 in pairs(t3) do  -- qtype
			table.insert(counts, t4["#count"])
		    end
	    end
        end
    end
    return counts
end

local function reg_counts(unique)
    -- extract unique[reg_name][nlabels][qtype]["#count"]
    for reg_name, t2 in pairs(unique) do  -- reg_name
        if t2['#queries'] > 2 then
            local weight_per_q = math.ceil(t2['#queries'] / t2['#outputs'])
            for _, t3 in pairs(t2) do  -- nlabes
                if type(t3) == 'table' then
                    for qtype, t4 in pairs(t3) do  -- qtype
                        for qname, istrue in pairs(t4) do  -- qtype
                            if istrue == true then
                                print(string.format("%s\t%s\t%d", qname, qtype, weight_per_q))
                            end
                        end
                    end
                end
            end
        end
    end
end


for n = 2, #arg do
    local pcap_input = input.new()
    local pkts = 0
    pcap_input:open_offline(arg[n])
    io.stderr:write(string.format("opened %s\n", arg[n]))
    local pcap_layer = layer.new()
    pcap_layer:producer(pcap_input)
    local producer, ctx = pcap_layer:produce()

    while true do
        local obj = producer(ctx)
        if obj == nil then break end
	pkts = pkts + 1
	if pkts % 1000000 == 0 then
            io.stderr:write(string.format("processed %.0f M pkts\n", pkts / 1e6))
        end
        local pl = obj:cast()
        if obj:type() == "payload" and pl.len > 0 then
            process_packet(obj)
        end
    end
end

--print(pprint(unique, 'error'))
reg_counts(unique)
local counts = dn_counts(unique)

io.stderr:write(string.format("median dn_limit: %.2f\n", stats.median(counts)))
io.stderr:write(string.format("mean dn_limit: %.2f\n", stats.mean(counts)))
