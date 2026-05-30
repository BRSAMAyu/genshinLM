from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class QuestStep:
    step_id: str
    description: str
    objective: str
    prereq_ar: int = 0
    prereq_quest: str = ""
    region: str = ""
    npc_name: str = ""
    auto_navigate: bool = True
    has_combat: bool = False
    has_dialog: bool = False
    has_cutscene: bool = False


@dataclass(slots=True)
class ArchonQuest:
    quest_id: str
    chapter: str
    title: str
    steps: list[QuestStep]
    completion_reward: str = ""


ARCHON_QUESTS: list[ArchonQuest] = [
    ArchonQuest("AQ001", "序章·第一幕", "捕风的异乡人", [
        QuestStep("AQ001_01", "与安柏对话", objective="dialog_complete",
                  npc_name="安柏", region="mondstadt", has_dialog=True),
        QuestStep("AQ001_02", "前往蒙德城", objective="reached_mondstadt",
                  region="mondstadt", auto_navigate=True),
        QuestStep("AQ001_03", "与骑士团成员交谈", objective="dialog_complete",
                  region="mondstadt", has_dialog=True),
        QuestStep("AQ001_04", "前往风神像", objective="reached_statue",
                  region="mondstadt", auto_navigate=True),
        QuestStep("AQ001_05", "与温迪对话", objective="dialog_complete",
                  npc_name="温迪", region="mondstadt", has_dialog=True, has_cutscene=True),
        QuestStep("AQ001_06", "击败风魔龙", objective="combat_complete",
                  region="mondstadt", has_combat=True, has_cutscene=True),
        QuestStep("AQ001_07", "与温迪交谈", objective="dialog_complete",
                  npc_name="温迪", region="mondstadt", has_dialog=True),
    ]),
    ArchonQuest("AQ002", "序章·第二幕", "为了没有眼泪的明天", [
        QuestStep("AQ002_01", "前往骑士团总部", objective="reached_knights_hq",
                  region="mondstadt", auto_navigate=True),
        QuestStep("AQ002_02", "与琴交谈", objective="dialog_complete",
                  npc_name="琴", region="mondstadt", has_dialog=True),
        QuestStep("AQ002_03", "寻找风神瞳", objective="item_collected",
                  region="mondstadt", auto_navigate=True),
        QuestStep("AQ002_04", "返回向琴汇报", objective="dialog_complete",
                  npc_name="琴", region="mondstadt", has_dialog=True),
    ]),
    ArchonQuest("AQ003", "序章·第三幕", "巨龙与自由之歌", [
        QuestStep("AQ003_01", "前往风龙废墟", objective="reached_dragonruins",
                  region="mondstadt", auto_navigate=True, has_combat=True),
        QuestStep("AQ003_02", "进入风龙废墟", objective="entered_domain",
                  region="mondstadt"),
        QuestStep("AQ003_03", "击败深渊法师", objective="combat_complete",
                  region="mondstadt", has_combat=True),
        QuestStep("AQ003_04", "净化风魔龙", objective="dialog_complete",
                  has_cutscene=True, has_dialog=True),
        QuestStep("AQ003_05", "与众人对话", objective="dialog_complete",
                  region="mondstadt", has_dialog=True, has_cutscene=True),
    ]),
    # Placeholder for remaining Archon Quests (Chapter 1-5)
    # These will be filled in with actual quest steps
    ArchonQuest("AQ004", "第一章·第一幕", "浮世浮生千岩间", [
        QuestStep("AQ004_01", "前往璃月", objective="reached_liyue",
                  region="liyue", auto_navigate=True, prereq_ar=23),
        QuestStep("AQ004_02", "与刻晴对话", objective="dialog_complete",
                  npc_name="刻晴", region="liyue", has_dialog=True),
        QuestStep("AQ004_03", "参加请仙典仪", objective="dialog_complete",
                  region="liyue", has_dialog=True, has_cutscene=True),
        QuestStep("AQ004_04", "逃离千岩军追捕", objective="escape_complete",
                  region="liyue", auto_navigate=True),
        QuestStep("AQ004_05", "与仙人对话", objective="dialog_complete",
                  region="liyue", has_dialog=True),
    ]),
    ArchonQuest("AQ005", "第一章·第二幕", "辞行久远之躯", [
        QuestStep("AQ005_01", "调查岩神遇害现场", objective="investigation_complete",
                  region="liyue", prereq_ar=26),
        QuestStep("AQ005_02", "与魈对话", objective="dialog_complete",
                  npc_name="魈", region="liyue", has_dialog=True, has_combat=True),
        QuestStep("AQ005_03", "击败遗迹猎者", objective="combat_complete",
                  region="liyue", has_combat=True),
        QuestStep("AQ005_04", "向仙人汇报", objective="dialog_complete",
                  region="liyue", has_dialog=True),
    ]),
    # Chapter 2: Inazuma
    ArchonQuest("AQ006", "第一章·第三幕", "迫近的客星", [
        QuestStep("AQ006_01", "前往黄金屋", objective="reached_golden_house",
                  region="liyue", auto_navigate=True, prereq_ar=28),
        QuestStep("AQ006_02", "与公子战斗", objective="combat_complete",
                  region="liyue", has_combat=True, has_cutscene=True),
        QuestStep("AQ006_03", "追击达达利亚", objective="pursuit_complete",
                  region="liyue", has_combat=True),
        QuestStep("AQ006_04", "与钟离对话", objective="dialog_complete",
                  npc_name="钟离", region="liyue", has_dialog=True, has_cutscene=True),
        QuestStep("AQ006_05", "岩王帝君告别仪式", objective="dialog_complete",
                  region="liyue", has_dialog=True, has_cutscene=True),
    ]),
    ArchonQuest("AQ_CH2_01", "第二章·第一幕", "不动鸣神 恒常乐土", [
        QuestStep("AQ_CH2_01_01", "前往稻妻", objective="reached_inazuma",
                  region="inazuma", auto_navigate=True, prereq_ar=30),
        QuestStep("AQ_CH2_01_02", "在离岛办理手续", objective="dialog_complete",
                  region="inazuma", has_dialog=True),
        QuestStep("AQ_CH2_01_03", "前往鸣神岛·探索稻妻城", objective="reached_inazuma_city",
                  region="inazuma", auto_navigate=True),
        QuestStep("AQ_CH2_01_04", "接触反抗军相关剧情", objective="dialog_complete",
                  region="inazuma", has_dialog=True, has_combat=True),
        QuestStep("AQ_CH2_01_05", "雷电将军Boss战", objective="combat_complete",
                  region="inazuma", has_combat=True, has_cutscene=True),
    ]),
    # Chapter 3: Sumeru
    ArchonQuest("AQ_CH3_01", "第三章·第一幕", "穿越烟帷与暗林", [
        QuestStep("AQ_CH3_01_01", "前往须弥城", objective="reached_sumeru",
                  region="sumeru", auto_navigate=True, prereq_ar=35),
        QuestStep("AQ_CH3_01_02", "接触教令院", objective="dialog_complete",
                  region="sumeru", has_dialog=True),
        QuestStep("AQ_CH3_01_03", "梦境虚空相关任务", objective="dream_loop_complete",
                  region="sumeru", has_dialog=True, has_cutscene=True),
        QuestStep("AQ_CH3_01_04", "正机之神Boss战", objective="combat_complete",
                  region="sumeru", has_combat=True, has_cutscene=True),
    ]),
    # Chapter 4: Fontaine
    ArchonQuest("AQ_CH4_01", "第四章·第一幕", "始如冬日之犬", [
        QuestStep("AQ_CH4_01_01", "前往枫丹廷", objective="reached_fontaine",
                  region="fontaine", auto_navigate=True, prereq_ar=40),
        QuestStep("AQ_CH4_01_02", "参与歌剧院审判", objective="dialog_complete",
                  region="fontaine", has_dialog=True, has_cutscene=True),
        QuestStep("AQ_CH4_01_03", "枫丹水下探索", objective="underwater_explore_complete",
                  region="fontaine"),
        QuestStep("AQ_CH4_01_04", "梅洛彼得堡相关剧情", objective="dialog_complete",
                  region="fontaine", has_dialog=True),
    ]),
    # Chapter 5: Natlan
    ArchonQuest("AQ_CH5_01", "第五章·第一幕", "荣花与炎日之途", [
        QuestStep("AQ_CH5_01_01", "前往圣火竞技场", objective="reached_natlan",
                  region="natlan", auto_navigate=True, prereq_ar=45),
        QuestStep("AQ_CH5_01_02", "参与巡礼仪式", objective="combat_complete",
                  region="natlan", has_combat=True, has_dialog=True),
        QuestStep("AQ_CH5_01_03", "探索纳塔各部落", objective="exploration_complete",
                  region="natlan", auto_navigate=True),
        QuestStep("AQ_CH5_01_04", "纳塔最终Boss战", objective="combat_complete",
                  region="natlan", has_combat=True, has_cutscene=True),
    ]),
]
