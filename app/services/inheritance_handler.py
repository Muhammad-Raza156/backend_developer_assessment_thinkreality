from typing import List, Dict, Any
from uuid import UUID

class InheritanceHandler:
    async def validate_heirs(self, deceased_owner_id: UUID, heirs: List[Dict[str, Any]]) -> bool:
        # Placeholder logic: Confirm heir relationships (e.g., from a mock relationship DB)
        return True

    async def calculate_islamic_distribution(self, deceased_owner_id: UUID, heirs: List[Dict[str, Any]]) -> Dict[str, int]:
        no_of_wives=0
        no_of_daughters=0
        no_of_sons=0
        for heir in heirs:
            if heir.get('name')=='wife':
                no_of_wives+=1
            elif heir.get('name')=='son':
                no_of_sons+=1
            elif heir.get('name')=='daughter':
                no_of_daughters+=1

        
        return {
            "number_of_wives": no_of_wives,
            "number_of_daughters": no_of_daughters,
            "number_of_sons": no_of_sons
            }

    async def handle_inheritance_transfer(self, unit_id: UUID, deceased_owner_id: UUID,ownership_percentage: float, heirs: List[Dict[str, Any]]):
        if not self.validate_heirs(deceased_owner_id, heirs):
            raise ValueError("Invalid heir relationship")
        
        islamic_distribution=self.calculate_islamic_distribution(deceased_owner_id, heirs)
        rest_shares=0.0
        share_of_one_wife=0.0
        daughter_share=0.0
        son_share=0.0
        if islamic_distribution['no_of_wives']>0:
            # As per hanfi school of thought property share of all wives is 1/8th
            wives_share=ownership_percentage/8
            share_of_one_wife=wives_share/islamic_distribution['no_of_wives']
            rest_shares=ownership_percentage-wives_share
        if islamic_distribution['no_of_wives']==0:
            rest_shares=ownership_percentage
        if islamic_distribution['no_of_daughters']!=0 and islamic_distribution['no_of_sons']==0:
            # As per hanfi school of thought if ther are daughters only 
            # then all property is distributed equally among them 
            daughter_share=rest_shares/islamic_distribution['no_of_daughters']
        elif islamic_distribution['no_of_sons']!=0 and islamic_distribution['no_of_daughters']==0:
            # As per hanfi school of thought if ther are sons only 
            # then all property is distributed equally among them 
            son_share=rest_shares/islamic_distribution['no_of_sons']
        elif islamic_distribution['no_of_sons']>0 and islamic_distribution['no_of_daughters']>0:
            # As per hanfi school of thought share of a daughter is half of the share of son
            total_children_shares=2*islamic_distribution['no_of_sons']+islamic_distribution['no_of_daughters']
            one_child_share=rest_shares/total_children_shares
            son_share=one_child_share*2
            daughter_share=one_child_share
        
        inheritance_shares={"name":"", "share":0}
        for key, value in heirs.items():
            if value=='wife':
                inheritance_shares['name']=key
                inheritance_shares['share']=share_of_one_wife
            elif value=='daughter':
                inheritance_shares['name']=key
                inheritance_shares['share']=daughter_share
            elif value == 'sone':
                inheritance_shares['name']=key
                inheritance_shares['share']=son_share
        
        return inheritance_shares